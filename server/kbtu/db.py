"""SQLite: one file, WAL, foreign keys on (SPEC §5). Each request takes a connection of its own from a Pool (threads
and worker processes stay apart); a write that checks and then inserts (the last seat) runs inside `tx`, which takes
the write lock up front (BEGIN IMMEDIATE), so two requests can't both see a free seat."""
from __future__ import annotations

import contextlib
import fcntl
import queue
import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path

SCHEMA = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
# Changes after the base schema: (user_version they bring the file to, SQL). Append only; mirror in SPEC §5.
def held_by(x: str) -> str:
    """SQL: the club that holds Telegram chat `x` (its chat sync link, else its chats card, else its newest event's
    chat), as logic.chatlist._holder reads it."""
    return f"""COALESCE((SELECT org_id FROM chat_sync WHERE chat_id = {x}),
      (SELECT org_id FROM chats WHERE tg_chat_id = {x} AND org_id IS NOT NULL ORDER BY id LIMIT 1),
      (SELECT org_id FROM events WHERE chat_id = {x} AND org_id IS NOT NULL ORDER BY id DESC LIMIT 1))"""


def _seen_triggers() -> str:
    """chat_seen rows go the moment their chat is no longer their club's: any link to the chat made, changed or removed."""
    out = []
    for table, col in (("chat_sync", "chat_id"), ("chats", "tg_chat_id"), ("events", "chat_id")):
        for op, refs in (("INSERT", ("NEW",)), ("DELETE", ("OLD",)), (f"UPDATE OF {col}, org_id", ("OLD", "NEW"))):
            when = f" WHEN OLD.{col} IS NOT NEW.{col} OR OLD.org_id IS NOT NEW.org_id" if len(refs) == 2 else ""
            body = "".join(f"\n  DELETE FROM chat_seen WHERE chat_id = {r}.{col} AND org_id IS NOT {held_by(f'{r}.{col}')};" for r in refs)
            out.append(f"CREATE TRIGGER chat_seen_{table}_{op.split()[0].lower()} AFTER {op} ON {table}{when} BEGIN{body}\nEND;")
    return "\n".join(out)


_CHAT_SEEN = """CREATE TABLE chat_seen (
  chat_id INTEGER NOT NULL,
  tg_id INTEGER NOT NULL,
  org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  seen_at INTEGER NOT NULL,
  PRIMARY KEY (chat_id, tg_id)) STRICT, WITHOUT ROWID;
""" + _seen_triggers()


MIGRATIONS: list[tuple[int, str]] = [
    (2, "ALTER TABLE files ADD COLUMN color TEXT;"),   # a photo's average colour: the event sheet's tint
    # a club's socials (Instagram, TikTok, YouTube, Telegram, a site), shown on its sheet; the old single link moves in
    (3, "ALTER TABLE orgs ADD COLUMN links TEXT NOT NULL DEFAULT '[]'; UPDATE orgs SET links = json_array(link) WHERE link IS NOT NULL;"),
    # join applications (§4.5): the club opens or closes them in Studio (closed by default since 66); the "recruiting until" date goes
    (4, "ALTER TABLE orgs ADD COLUMN recruiting INTEGER NOT NULL DEFAULT 1; UPDATE orgs SET recruiting = 0 WHERE kind IN ('school','office','app');"
        " ALTER TABLE orgs DROP COLUMN recruiting_until;"),
    # the badge QR (§4.4): a random code per student, so nobody can make a QR from a user id;
    # walk_in marks a registration made at the door with that QR
    (5, "ALTER TABLE users ADD COLUMN qr_code TEXT; CREATE UNIQUE INDEX users_qr ON users(qr_code);"
        " ALTER TABLE registrations ADD COLUMN walk_in INTEGER NOT NULL DEFAULT 0;"),
    # the point of the cover every frame keeps in view, "x,y" from 0 to 1 (Oct 4: one photo fills a tall Feed slide,
    # the wide sheet and a square thumbnail, so the organizer marks what matters instead of one crop)
    (6, "ALTER TABLE events ADD COLUMN cover_focus TEXT;"),
    # checked in by name at the door (no QR: a dead phone), shown "by hand" to the organizer and in the CSV
    (7, "ALTER TABLE registrations ADD COLUMN checkin_manual INTEGER NOT NULL DEFAULT 0;"),
    # an organizer's update on an event, pinned under its title; the bot only says there is one
    (8, """CREATE TABLE event_updates (
        id INTEGER PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        body TEXT NOT NULL CHECK (length(body) BETWEEN 2 AND 300),
        created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX event_updates_by_event ON event_updates(event_id, created_at);"""),
    # one-tap rating after an event: only people checked in, anonymous to the club
    (9, """CREATE TABLE event_ratings (
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
        comment TEXT NOT NULL DEFAULT '' CHECK (length(comment) <= 300),
        created_at INTEGER NOT NULL,
        PRIMARY KEY (event_id, user_id)
    ) STRICT;"""),
    # the personal calendar feed: everything I go to, subscribed once in the phone's calendar
    (10, """ALTER TABLE users ADD COLUMN cal_token TEXT;
    CREATE UNIQUE INDEX users_cal_token ON users(cal_token);"""),
    # the unlock moment: the level the app has already celebrated (the bot's message goes once by its own ref)
    (11, "ALTER TABLE achievement_levels ADD COLUMN seen INTEGER NOT NULL DEFAULT 0;"),
    # a student's number on the card: the order of first KBTU sign-in, kept for good; the Creator's card shows 00000 and
    # takes none, so "First 500" is the cards 00001-00500. Students so far: by when they signed in.
    (12, """ALTER TABLE users ADD COLUMN card_no INTEGER;
    CREATE UNIQUE INDEX users_card_no ON users(card_no);
    UPDATE users SET card_no = (SELECT n FROM (SELECT s.user_id, ROW_NUMBER() OVER (ORDER BY s.verified_at, s.user_id) AS n
            FROM students s JOIN users x ON x.id = s.user_id WHERE x.is_founder = 0) r WHERE r.user_id = users.id)
        WHERE is_founder = 0 AND id IN (SELECT user_id FROM students);"""),
    # a registration deadline (NULL = until the start), and a paid event's free seats for 1st-year students: "the first
    # 100 tickets free for the 1st course"; `free` marks a registration holding one of them
    (13, """ALTER TABLE events ADD COLUMN reg_until INTEGER;
    ALTER TABLE events ADD COLUMN free_first INTEGER CHECK (free_first > 0);
    ALTER TABLE registrations ADD COLUMN free INTEGER NOT NULL DEFAULT 0;"""),
    # Team 2.0 (SPEC §2b): a club's own roles (a name and colour on one of the levels), tags (groups of
    # people), probation with strikes, removal by request (a Head asks, the President or Vice decide), club bans
    (14, """CREATE TABLE org_roles (
        id INTEGER PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        color TEXT NOT NULL,
        level TEXT NOT NULL CHECK (level IN ('member','head','vice')),
        created_at INTEGER NOT NULL
    ) STRICT;
    CREATE UNIQUE INDEX org_roles_name ON org_roles(org_id, lower(name));
    ALTER TABLE org_members ADD COLUMN role_id INTEGER REFERENCES org_roles(id) ON DELETE SET NULL;
    ALTER TABLE org_members ADD COLUMN probation INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE org_tags (
        id INTEGER PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        color TEXT NOT NULL,
        created_at INTEGER NOT NULL
    ) STRICT;
    CREATE UNIQUE INDEX org_tags_name ON org_tags(org_id, lower(name));
    CREATE TABLE member_tags (
        tag_id INTEGER NOT NULL REFERENCES org_tags(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        PRIMARY KEY (tag_id, user_id)
    ) STRICT;
    CREATE TABLE strikes (
        id INTEGER PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reason TEXT NOT NULL CHECK (reason IN ('meeting','event','other')),
        note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 140),
        by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at INTEGER NOT NULL,
        cleared_at INTEGER,
        cleared_by INTEGER REFERENCES users(id) ON DELETE SET NULL
    ) STRICT;
    CREATE INDEX strikes_by_member ON strikes(org_id, user_id);
    CREATE TABLE removal_requests (
        id INTEGER PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        ban INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 140),
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','declined')),
        created_at INTEGER NOT NULL,
        decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        decided_at INTEGER
    ) STRICT;
    CREATE UNIQUE INDEX one_removal_ask ON removal_requests(org_id, user_id) WHERE status = 'pending';
    CREATE TABLE org_bans (
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (org_id, user_id)
    ) STRICT;"""),
    # Studio's "questions waiting" go once the reader has read them:
    # the newest comment under an event when each of the club's Head+ last opened them (ids, not seconds: exact)
    (15, """CREATE TABLE comment_reads (
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        last_id INTEGER NOT NULL,
        PRIMARY KEY (event_id, user_id)
    ) STRICT;"""),
    # a nickname and my own photo (SPEC §3): everyone sees the nick, organizers the real name beside it;
    # avatar_tg is the "Photo from Telegram" switch, off once I upload my own (it goes in users.avatar_file_id)
    (16, """ALTER TABLE users ADD COLUMN nick TEXT CHECK (nick IS NULL OR length(nick) BETWEEN 2 AND 24);
    ALTER TABLE users ADD COLUMN avatar_tg INTEGER NOT NULL DEFAULT 1;"""),
    # wrong KBTU passwords per account (§4.1: 5 in 15 min) in the database, so every worker process counts the same ones;
    # two partial indexes the load test asked for: expired holds (swept before every Afisha) and "Life of the
    # party" (friends someone brought), each a scan of all registrations without one
    (17, """CREATE TABLE login_fails (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX login_fails_by_user ON login_fails(user_id, at);
    CREATE INDEX regs_holds ON registrations(hold_until) WHERE status = 'hold';
    CREATE INDEX regs_by_inviter ON registrations(invited_by) WHERE invited_by IS NOT NULL;"""),
    # no KBTU session is kept since Oct 7 (§4.1): the stored ones were ended at Keycloak, the table goes
    (18, "DROP TABLE IF EXISTS portal_sessions;"),
    # Studio part 2 "Meetings" (owner's go; SPEC §2b): a team-only event the whole club (or one tag) is expected at;
    # "Can't make it" says why (registrations.note); a missed meeting's strike names it, one per meeting per person
    (19, """ALTER TABLE events ADD COLUMN meeting INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE events ADD COLUMN meeting_tag INTEGER REFERENCES org_tags(id) ON DELETE SET NULL;
    ALTER TABLE registrations ADD COLUMN note TEXT CHECK (note IS NULL OR length(note) <= 140);
    ALTER TABLE strikes ADD COLUMN event_id INTEGER REFERENCES events(id) ON DELETE SET NULL;
    CREATE UNIQUE INDEX one_strike_per_meeting ON strikes(event_id, user_id) WHERE event_id IS NOT NULL;"""),
    # the server's own notes between starts: the achievements list the levels were last recorded for
    (20, "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"),
    (21, "ALTER TABLE users ADD COLUMN mark TEXT;"),  # a person's mark by the name besides the Creator's: 'idea' (SPEC §1)
    (22, "ALTER TABLE org_roles ADD COLUMN rights TEXT;"),  # a club role's toggles, comma-separated; NULL: its level's (SPEC §2)
    # what the club asks DMP for in its weekly memo (PLAN "Memo in one tap"): JSON, the editor's "For the memo" block
    (23, "ALTER TABLE events ADD COLUMN memo TEXT;"),
    # the in-app room booking demo goes (owner's yes): DMP books rooms by memo (§4.12c)
    (24, "DROP TABLE IF EXISTS room_requests;"),
    # casting (PLAN "Casting"): a club's recruitment round, its departments (the club's tags) and own questions, the
    # applications (what the student picked and answered; the rest is their KBTU profile) and the team's votes
    (25, """CREATE TABLE rounds (
        id INTEGER PRIMARY KEY,
        org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        picks INTEGER NOT NULL DEFAULT 2 CHECK (picks BETWEEN 1 AND 3),
        closes_at INTEGER NOT NULL,
        results_by INTEGER,
        decline_text TEXT NOT NULL DEFAULT '' CHECK (length(decline_text) <= 500),
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'done')),
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at INTEGER NOT NULL,
        sent_at INTEGER
    ) STRICT;
    CREATE UNIQUE INDEX one_live_round ON rounds(org_id) WHERE status != 'done';
    CREATE TABLE round_departments (
        round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
        tag_id INTEGER NOT NULL REFERENCES org_tags(id) ON DELETE CASCADE,
        pos INTEGER NOT NULL,
        about TEXT NOT NULL DEFAULT '' CHECK (length(about) <= 200),
        places INTEGER CHECK (places > 0),
        PRIMARY KEY (round_id, tag_id)
    ) STRICT;
    CREATE TABLE round_questions (
        id INTEGER PRIMARY KEY,
        round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
        pos INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('short', 'long', 'one', 'many', 'link')),
        text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 200),
        options TEXT,
        required INTEGER NOT NULL DEFAULT 1,
        tag_id INTEGER REFERENCES org_tags(id) ON DELETE SET NULL
    ) STRICT;
    CREATE TABLE round_apps (
        id INTEGER PRIMARY KEY,
        round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        departments TEXT NOT NULL,
        answers TEXT NOT NULL,
        source TEXT,
        stage TEXT NOT NULL DEFAULT 'new' CHECK (stage IN ('new', 'maybe', 'next', 'yes', 'no', 'withdrawn')),
        taken_tag INTEGER REFERENCES org_tags(id) ON DELETE SET NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE (round_id, user_id)
    ) STRICT;
    CREATE TABLE round_votes (
        app_id INTEGER NOT NULL REFERENCES round_apps(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        verdict TEXT NOT NULL CHECK (verdict IN ('no', 'maybe', 'next')),
        stars INTEGER CHECK (stars BETWEEN 1 AND 5),
        note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 500),
        at INTEGER NOT NULL,
        PRIMARY KEY (app_id, user_id)
    ) STRICT;"""),
    # casting's interviews: the team's time slots (one by one, or a group: capacity), each shortlisted
    # application's slot, when it was invited, whether they came
    (26, """CREATE TABLE round_slots (
        id INTEGER PRIMARY KEY,
        round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
        starts_at INTEGER NOT NULL,
        minutes INTEGER NOT NULL CHECK (minutes BETWEEN 5 AND 180),
        capacity INTEGER NOT NULL DEFAULT 1 CHECK (capacity BETWEEN 1 AND 50),
        place TEXT NOT NULL DEFAULT '' CHECK (length(place) <= 120)
    ) STRICT;
    CREATE INDEX slots_by_round ON round_slots(round_id, starts_at);
    ALTER TABLE round_apps ADD COLUMN slot_id INTEGER REFERENCES round_slots(id) ON DELETE SET NULL;
    ALTER TABLE round_apps ADD COLUMN invited_at INTEGER;
    ALTER TABLE round_apps ADD COLUMN came INTEGER;"""),
    # a class's subject in ru / kk / en (JSON), so the schedule follows the app's language
    (27, "ALTER TABLE schedule_classes ADD COLUMN names TEXT;"),
    # the album: a photo can be reported (the table gains 'photo' in its CHECK: rebuilt), and an event
    # can keep its album to the team (album_open = 0: "Photos from participants" off)
    (28, """CREATE TABLE reports2 (
        id INTEGER PRIMARY KEY,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        target TEXT NOT NULL CHECK (target IN ('post', 'comment', 'event', 'user', 'org', 'photo')),
        target_id INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK (reason IN ('spam', 'insult', 'danger', 'other')),
        note TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
        created_at INTEGER NOT NULL,
        resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        resolved_at INTEGER
    ) STRICT;
    INSERT INTO reports2 SELECT id, reporter_id, target, target_id, reason, note, status, created_at, resolved_by, resolved_at FROM reports;
    DROP TABLE reports;
    ALTER TABLE reports2 RENAME TO reports;
    CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id);
    ALTER TABLE events ADD COLUMN album_open INTEGER NOT NULL DEFAULT 1;"""),
    # memo v2 (PLAN stage 2): the sender's signature fixed once (JSON: nameEn, kk, ru, en), which events went to DMP,
    # who opened the week's memo last; the right "memo" (the secretary's), given to every club role that runs the team
    (29, """ALTER TABLE org_members ADD COLUMN memo_sign TEXT;
    ALTER TABLE events ADD COLUMN memo_sent_at INTEGER;
    ALTER TABLE events ADD COLUMN memo_sent_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    ALTER TABLE orgs ADD COLUMN memo_opened_at INTEGER;
    ALTER TABLE orgs ADD COLUMN memo_opened_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    UPDATE org_roles SET rights = rights || ',memo' WHERE ',' || rights || ',' LIKE '%,team,%';"""),
    # comment replies (PLAN "Comment replies"): the comment answered, quoted above the reply; its author hears it
    (30, "ALTER TABLE comments ADD COLUMN reply_to INTEGER REFERENCES comments(id) ON DELETE SET NULL;"),
    # the admin's stats (PLAN "Admin stats"): one row a day from users.seen_at, counts only, no per-person log
    (31, """CREATE TABLE stats_days (
        day INTEGER PRIMARY KEY,                -- days since 1970-01-01 in Almaty
        active INTEGER NOT NULL,                -- people who opened the app that day
        new INTEGER NOT NULL,                   -- people who opened it for the first time
        students INTEGER NOT NULL               -- signed in with KBTU by the day's end
    ) STRICT;"""),
    # badge skins: the club whose badge I show; NULL = the KBTU one. Only an official club I'm in counts
    (32, "ALTER TABLE users ADD COLUMN skin_org INTEGER REFERENCES orgs(id) ON DELETE SET NULL;"),
    # the creator's one-time award link (a bug report comes in a chat, not face to face)
    (33, """CREATE TABLE grant_links (
        token TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        used_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        used_at INTEGER
    ) STRICT;"""),
    # what I picked for my badge myself: NULL never (a new club's badge comes by itself), 'kbtu', 'org'
    # (skin_org), 'sower' (the creator's own)
    (34, """ALTER TABLE users ADD COLUMN skin_pick TEXT CHECK (skin_pick IN ('kbtu', 'org', 'sower'));
    UPDATE users SET skin_pick = 'org' WHERE skin_org IS NOT NULL;"""),
    # "delete my account" waits a week (a change of heart shouldn't cost the awards): when it goes
    (35, "ALTER TABLE users ADD COLUMN delete_at INTEGER;"),
    # "First 500" for the cards 1-500 that never got it ("95%" with fewer than 500 people): the pilot
    # signed in while it was "First 50", and a card handed out by /me skipped the award; quietly, no notification
    (36, """INSERT INTO achievement_grants (user_id, code, note, created_at)
        SELECT u.id, 'first50', 'backfill', CAST(strftime('%s', 'now') AS INTEGER) FROM users u JOIN students s ON s.user_id = u.id
        WHERE s.consent_version != 'staff' AND (u.is_founder = 1 OR u.card_no <= 500)
        AND NOT EXISTS (SELECT 1 FROM achievement_grants g WHERE g.user_id = u.id AND g.code = 'first50');
    INSERT INTO achievement_levels (user_id, code, level, reached_at, seen)
        SELECT g.user_id, 'first50', 1, g.created_at, 1 FROM achievement_grants g WHERE g.code = 'first50' AND g.note = 'backfill' AND true
        ON CONFLICT (user_id, code) DO UPDATE SET level = MAX(level, 1);"""),
    # the chats directory takes each chat's avatar (and title, members) from its t.me page (owner, Oct 14: "why doesn't
    # it take the channel's own picture"); a topics group is a group with forum = 1 (Telegram draws it as a squircle)
    (37, "ALTER TABLE chats ADD COLUMN photo TEXT; ALTER TABLE chats ADD COLUMN forum INTEGER NOT NULL DEFAULT 0;"),
    # a club's name and description in Kazakh and English (JSON {"kk": {"name", "description"}, "en": ...}); the base
    # columns are Russian. Filled for KBTU's schools from kbtu.edu.kz (logic.seed_schools)
    (38, "ALTER TABLE orgs ADD COLUMN i18n TEXT;"),
    # an event's short vertical video (video.py): uploading in pieces -> queued -> working (the postman
    # compresses) -> ready or failed. `path`: media/<path>.mp4 and its poster as a photo of the same name
    (39, """CREATE TABLE videos (
      id         INTEGER PRIMARY KEY,
      owner_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
      status     TEXT NOT NULL CHECK (status IN ('uploading','queued','working','ready','failed')),
      size       INTEGER NOT NULL,
      path       TEXT,
      width      INTEGER,
      height     INTEGER,
      duration   REAL,
      bytes      INTEGER,
      color      TEXT,
      error      TEXT,
      created_at INTEGER NOT NULL
    ) STRICT;
    ALTER TABLE events ADD COLUMN video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL;"""),
    # the three official roles every club has: President (the level, one per club), "Vice"
    # and "Head" as fixed roles (no rename, no delete; their rights below their level may be tuned). A role of that name
    # already there becomes the official one; Vices and Heads without a role name get it
    (40, """ALTER TABLE org_roles ADD COLUMN fixed INTEGER NOT NULL DEFAULT 0;
    UPDATE org_roles SET fixed = 1, level = 'vice', rights = NULL WHERE lower(name) IN ('vice', 'vice president');
    UPDATE org_roles SET fixed = 1, level = 'head', rights = NULL WHERE lower(name) = 'head';
    INSERT INTO org_roles (org_id, name, color, level, fixed, created_at)
      SELECT id, 'Vice', '#7C4DFF', 'vice', 1, CAST(strftime('%s', 'now') AS INTEGER) FROM orgs WHERE id NOT IN (SELECT org_id FROM org_roles WHERE fixed = 1 AND level = 'vice');
    INSERT INTO org_roles (org_id, name, color, level, fixed, created_at)
      SELECT id, 'Head', '#3B6BFF', 'head', 1, CAST(strftime('%s', 'now') AS INTEGER) FROM orgs WHERE id NOT IN (SELECT org_id FROM org_roles WHERE fixed = 1 AND level = 'head');
    UPDATE org_members SET role_id = (SELECT r.id FROM org_roles r WHERE r.org_id = org_members.org_id AND r.fixed = 1 AND r.level = org_members.role)
      WHERE role_id IS NULL AND role IN ('vice', 'head');"""),
    # unused since Oct 15 (requests without an event became the memo's templates); kept, migrations only append
    (41, "ALTER TABLE events ADD COLUMN memo_only INTEGER NOT NULL DEFAULT 0;"),
    # volunteers: how many an event needs (NULL: none), maybe not year 1; applications the organizer decides
    (42, """ALTER TABLE events ADD COLUMN volunteers INTEGER;
    ALTER TABLE events ADD COLUMN volunteers_senior INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE volunteers (
      event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status     TEXT NOT NULL CHECK (status IN ('asked', 'yes', 'no')),
      note       TEXT NOT NULL DEFAULT '',
      created_at INTEGER NOT NULL,
      decided_at INTEGER,
      PRIMARY KEY (event_id, user_id));"""),
    # an event's Telegram group (no userbot): the organizer adds the bot by a link carrying chat_token,
    # the bot keeps the group's id and its join-request link and lets in only those signed up
    (43, """ALTER TABLE events ADD COLUMN chat_id INTEGER;
    ALTER TABLE events ADD COLUMN chat_link TEXT;
    ALTER TABLE events ADD COLUMN chat_token TEXT;
    CREATE UNIQUE INDEX events_chat_token ON events(chat_token) WHERE chat_token IS NOT NULL;"""),
    # the events channel: the post of a public event, and what it says (an edit when that changes)
    (44, """ALTER TABLE events ADD COLUMN channel_msg INTEGER;
    ALTER TABLE events ADD COLUMN channel_photo INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE events ADD COLUMN channel_sig TEXT;"""),
    # indoor routes: the graph of corridors, stairs, lifts and exits he edits on the map; one row
    (45, """CREATE TABLE map_graph (id INTEGER PRIMARY KEY CHECK (id = 1), body TEXT NOT NULL, ver INTEGER NOT NULL,
    updated_by INTEGER, updated_at INTEGER NOT NULL);"""),
    # typed in by the student while the portal is out of reach: replaced by the portal's data on their
    # first real sign-in; until then their student ID is only their word
    (46, "ALTER TABLE students ADD COLUMN manual INTEGER NOT NULL DEFAULT 0;"),
    # who was where and when (a club leader, Oct 16: "ex-head of X, Oct 25 - May 26"; owner: recorded by itself, never
    # typed in). Triggers on org_members, so every way in, up, down and out is caught, now and in code written later
    (47, """CREATE TABLE org_history (
      id      INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      org_id  INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      role    TEXT NOT NULL,
      since   INTEGER NOT NULL,
      until   INTEGER                                -- NULL: still so
    ) STRICT;
    CREATE INDEX history_by_user ON org_history(user_id, org_id);
    INSERT INTO org_history (user_id, org_id, role, since) SELECT user_id, org_id, role, joined_at FROM org_members;
    CREATE TRIGGER history_in AFTER INSERT ON org_members BEGIN
      INSERT INTO org_history (user_id, org_id, role, since) VALUES (NEW.user_id, NEW.org_id, NEW.role, CAST(strftime('%s', 'now') AS INTEGER));
    END;
    CREATE TRIGGER history_role AFTER UPDATE OF role ON org_members WHEN OLD.role != NEW.role BEGIN
      UPDATE org_history SET until = CAST(strftime('%s', 'now') AS INTEGER) WHERE user_id = OLD.user_id AND org_id = OLD.org_id AND until IS NULL;
      INSERT INTO org_history (user_id, org_id, role, since) VALUES (NEW.user_id, NEW.org_id, NEW.role, CAST(strftime('%s', 'now') AS INTEGER));
    END;
    CREATE TRIGGER history_out AFTER DELETE ON org_members BEGIN
      UPDATE org_history SET until = CAST(strftime('%s', 'now') AS INTEGER) WHERE user_id = OLD.user_id AND org_id = OLD.org_id AND until IS NULL;
    END;"""),
    # an event's talk lives under its channel post in Telegram: the link to the bot's first comment there
    (48, "ALTER TABLE events ADD COLUMN channel_link TEXT;"),
    # the KBTU-password sign-in is gone: its wrong-password counter with it
    (49, "DROP TABLE IF EXISTS login_fails;"),
    # the KBTU Microsoft account a student signed in with (msauth.py): one account, one student
    (50, """ALTER TABLE students ADD COLUMN ms_oid TEXT;
        CREATE UNIQUE INDEX students_ms_oid ON students(ms_oid) WHERE ms_oid IS NOT NULL;"""),
    # everything Microsoft gives about the student, as it came (owner, Oct 20: "keep all we get, it's free"; the way
    # from typing it in to signing up by itself)
    (51, "ALTER TABLE students ADD COLUMN ms_profile TEXT;"),
    # a chat any student suggests through the bot waits for the admins (PLAN item 45); added_by is who
    (52, "ALTER TABLE chats ADD COLUMN status TEXT NOT NULL DEFAULT 'live';"),
    # departments (PLAN item 47): a tag marked as a department, one per person; a club's latest casting
    # round names its real ones (older rounds may hold tags that were never departments)
    (53, """ALTER TABLE org_tags ADD COLUMN department INTEGER NOT NULL DEFAULT 0;
        UPDATE org_tags SET department = 1 WHERE id IN (SELECT d.tag_id FROM round_departments d JOIN rounds r ON r.id = d.round_id
            WHERE r.id = (SELECT MAX(x.id) FROM rounds x WHERE x.org_id = r.org_id));"""),
    # a member link may put the newcomer straight into a department (PLAN 47: one who came by link landed in none)
    (54, "ALTER TABLE org_invites ADD COLUMN dept_id INTEGER REFERENCES org_tags(id) ON DELETE SET NULL;"),
    # an event's photos after the cover, swiped sideways (PLAN 33; event_photos is the guests' album), and a horizontal
    # video behind the event's sheet (PLAN 32): an upload says which slot it is for, so it is compressed for it
    (55, """CREATE TABLE event_slides (
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      pos      INTEGER NOT NULL,
      file_id  INTEGER NOT NULL REFERENCES files(id),
      PRIMARY KEY (event_id, pos)
    ) STRICT;
    ALTER TABLE events ADD COLUMN wide_video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL;
    ALTER TABLE videos ADD COLUMN wide INTEGER NOT NULL DEFAULT 0;"""),
    # texts in three languages by AI (PLAN 9, ai.py): i18n holds the other two languages, lang the source's (NULL: to
    # translate), ai_tries the failed calls since the last edit; schools have official translations (schools.json)
    (56, """ALTER TABLE events ADD COLUMN i18n TEXT;
    ALTER TABLE events ADD COLUMN lang TEXT;
    ALTER TABLE events ADD COLUMN ai_tries INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE orgs ADD COLUMN lang TEXT;
    ALTER TABLE orgs ADD COLUMN ai_tries INTEGER NOT NULL DEFAULT 0;
    UPDATE orgs SET lang = 'ru' WHERE kind = 'school';"""),
    # who opened the app on which day, for the admin's chart; 30 days, then
    # gone (stats_day); the privacy policy says so
    (57, """CREATE TABLE visits (
      day     INTEGER NOT NULL,   -- Almaty day number
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      PRIMARY KEY (day, user_id)
    ) WITHOUT ROWID;"""),
    # audit M3: since the portal sign-in closed (Oct 19, 00:00 Almaty) the year was typed in; it becomes the student
    # ID's (logic.course_of). The portal's own years stay: a repeater's ID is older than their year.
    (58, """UPDATE students SET course = MAX(1, MIN(6, CAST(strftime('%Y', 'now', '+5 hours') AS INTEGER)
        - (CAST(strftime('%m', 'now', '+5 hours') AS INTEGER) < 9) - (2000 + CAST(substr(student_id, 1, 2) AS INTEGER)) + 1))
      WHERE consent_at >= 1792350000 AND student_id GLOB '[0-9][0-9][A-Z]*' AND consent_version NOT IN ('staff', 'admin');"""),
    # card numbers at sign-in again: who signed in the night before, when a number waited for a first real
    # step, gets theirs now in the order they came, after every number given so far (burnt ones stay burnt)
    (59, """UPDATE users SET card_no = r.base + r.n FROM (SELECT s.user_id,
            ROW_NUMBER() OVER (ORDER BY s.verified_at, s.user_id) AS n,
            MAX((SELECT COALESCE(MAX(card_no), 0) FROM users),
                (SELECT COALESCE(MAX(CAST(value AS INTEGER)), 0) FROM meta WHERE key = 'card_last')) AS base
          FROM students s JOIN users x ON x.id = s.user_id
          WHERE x.card_no IS NULL AND x.is_founder = 0 AND x.tg_id > 0 AND s.manual = 0 AND s.consent_version != 'staff') r
        WHERE r.user_id = users.id;
      INSERT INTO meta (key, value) SELECT 'card_last', MAX(card_no) FROM users WHERE card_no IS NOT NULL HAVING MAX(card_no) IS NOT NULL
        ON CONFLICT (key) DO UPDATE SET value = MAX(CAST(value AS INTEGER), CAST(excluded.value AS INTEGER));"""),
    # club strikes are gone (never used, a lot of code for nothing); probation stays as a label
    (60, "DROP TABLE strikes; DELETE FROM bot_outbox WHERE kind = 'strike';"),
    # until now the sign-in demoted every admin missing from ADMIN_TG_IDS; it no longer does (roles are given in the
    # app), so a stale admin row from before must not wake up as an admin: those in the env get it back at sign-in
    (61, "UPDATE users SET role = 'user' WHERE role = 'admin' AND is_founder = 0;"),  # the owner never loses it
    # the year of study moves on every September 1 (logic.course_day): course_year is the academic year a course was
    # last right for: the one it was written in (synced_at, as course_day's fallback), or the ID's own for an August ID
    # of the coming intake. Then the years migration 58 read from the ID (typed-in rows, up to 6) stop at the degree's
    # last (bachelor 4, master 2): rows written since the portal closed (Oct 19; the typed-in sign-up
    # sets synced_at, ms_link then clears manual); the portal's own are never touched
    (62, """ALTER TABLE students ADD COLUMN course_year INTEGER;
    UPDATE students SET course_year = MAX(CAST(strftime('%Y', synced_at, 'unixepoch', '+5 hours') AS INTEGER)
        - (CAST(strftime('%m', synced_at, 'unixepoch', '+5 hours') AS INTEGER) < 9),
        CASE WHEN student_id GLOB '[0-9][0-9][A-Z]*' THEN 2000 + CAST(substr(student_id, 1, 2) AS INTEGER) ELSE 0 END)
      WHERE course IS NOT NULL;
    UPDATE students SET course = CASE substr(student_id, 3, 1) WHEN 'B' THEN 4 ELSE 2 END
      WHERE synced_at >= 1792350000 AND consent_version NOT IN ('staff', 'admin')
        AND ((student_id GLOB '[0-9][0-9]B*' AND course > 4) OR (student_id GLOB '[0-9][0-9]M*' AND course > 2));"""),
    # audit M2: strangers' profiles opened per day (logic._stranger_view); kept two days at most, no foreign keys
    # (delete_me clears a person's rows both ways)
    (63, """CREATE TABLE profile_views (
      day       INTEGER NOT NULL,   -- Almaty day number
      viewer_id INTEGER NOT NULL,
      user_id   INTEGER NOT NULL,
      PRIMARY KEY (day, viewer_id, user_id)
    ) WITHOUT ROWID;"""),
    # one report sheet for everything: one OPEN report per person and thing; once a moderator has
    # decided, the same person may report it again (it may have changed, or come back)
    (64, """DROP INDEX one_report;
    CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id) WHERE status = 'open';"""),
    # A4: a club application is a name, a description and up to 6 social links, no "why" essay: the
    # table again with links (JSON, the club's own rule) and why optional (old rows keep theirs). A19: the walk-ins at
    # the door without the app, by the full name they typed; linked when one confirms with Microsoft (logic.ms_link)
    (65, """CREATE TABLE club_applications_new (
      id          INTEGER PRIMARY KEY,
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      name        TEXT NOT NULL,
      short       TEXT NOT NULL,
      description TEXT NOT NULL,
      emoji       TEXT NOT NULL,
      cover       INTEGER NOT NULL,
      links       TEXT NOT NULL DEFAULT '[]',
      why         TEXT CHECK (length(why) BETWEEN 1 AND 500),
      status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
      reason      TEXT,
      org_id      INTEGER REFERENCES orgs(id) ON DELETE SET NULL,
      created_at  INTEGER NOT NULL,
      decided_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
      decided_at  INTEGER
    ) STRICT;
    INSERT INTO club_applications_new SELECT id, user_id, name, short, description, emoji, cover,
      CASE WHEN link IS NULL THEN '[]' ELSE json_array(link) END, why, status, reason, org_id, created_at, decided_by, decided_at
      FROM club_applications;
    DROP TABLE club_applications;
    ALTER TABLE club_applications_new RENAME TO club_applications;
    CREATE UNIQUE INDEX one_pending_application ON club_applications(user_id) WHERE status = 'pending';
    CREATE TABLE door_guests (
      id         INTEGER PRIMARY KEY,
      event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      full_name  TEXT NOT NULL,
      norm       TEXT NOT NULL,                     -- logic._norm_name: the words sorted, lowercase, yo as e
      added_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at INTEGER NOT NULL,
      user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL
    ) STRICT;
    CREATE INDEX door_guests_by_norm ON door_guests(norm) WHERE user_id IS NULL;"""),
    # recruiting is the club's own switch in Studio now: closed everywhere until a club opens it (owner, Oct 24: the list
    # of open clubs was every club); a round (Literature club's) shows on its own
    (66, "UPDATE orgs SET recruiting = 0;"),
    # 53/68: a club's members are public unless the club hides the list (a support group, a faith club)
    (67, "ALTER TABLE orgs ADD COLUMN members_hidden INTEGER NOT NULL DEFAULT 0;"),
    # a club's own short links kbtu.sow.kz/<slug>: only into the app, the club, one of its events, its round
    (68, """CREATE TABLE short_links (
        slug       TEXT PRIMARY KEY,                   -- logic.SHORT; never an orgs.slug or one a club had before
        org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        kind       TEXT NOT NULL CHECK (kind IN ('club', 'event', 'round')),
        event_id   INTEGER REFERENCES events(id) ON DELETE CASCADE,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at INTEGER NOT NULL,
        CHECK ((kind = 'event') = (event_id IS NOT NULL))
    ) STRICT;
    CREATE INDEX short_links_by_org ON short_links(org_id);"""),
    # PLAN 71: an event asks for the phone at sign-up (no up-front "My data" step); a phone already kept stays
    (69, "ALTER TABLE events ADD COLUMN needs_phone INTEGER NOT NULL DEFAULT 0;"),
    # a club's short name where a long one won't fit: its Vice+ or DMP set it; the clubs made before
    # take their initials at start (logic.fill_abbrs: SQLite can't uppercase Cyrillic); a school's comes from schools.json
    (70, "ALTER TABLE orgs ADD COLUMN abbr TEXT;"),
    # PLAN 86: a club's or school's own Telegram chats on its page: chats.org_id says whose a chat
    # is, main = its one channel with the Subscribe button (later the mirror's source), about = the chat's own line; one
    # linked only from Studio waits as status 'org', out of the shared catalog
    (71, """ALTER TABLE chats ADD COLUMN org_id INTEGER REFERENCES orgs(id) ON DELETE SET NULL;
    ALTER TABLE chats ADD COLUMN main INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE chats ADD COLUMN about TEXT;
    CREATE INDEX chats_by_org ON chats(org_id);
    CREATE UNIQUE INDEX chats_main ON chats(org_id) WHERE main = 1;"""),
    # PLAN 86 part 2: an org's main public channel mirrored into its news by the userbot (userbot.py, mirror.py).
    # chats.mirror: the club's switch in Studio; tg_channels: the channels the userbot joined itself (it leaves only
    # those), with the last post it took; a mirrored post knows its channel post (tg_url, views, Telegram's reaction
    # counts as JSON, a video or file only as a link) and every message it was made of (an album is one post)
    (72, """ALTER TABLE chats ADD COLUMN mirror INTEGER NOT NULL DEFAULT 1;
    CREATE TABLE tg_channels (
        id        INTEGER PRIMARY KEY,                -- Telegram's channel id (Telethon's, without -100)
        username  TEXT NOT NULL,                      -- lowercase, the t.me name it was joined by
        joined_at INTEGER NOT NULL,
        last_msg  INTEGER NOT NULL DEFAULT 0          -- the newest post taken: the catch-up after a restart starts there
    ) STRICT;
    ALTER TABLE posts ADD COLUMN tg_channel INTEGER;
    ALTER TABLE posts ADD COLUMN tg_url TEXT;
    ALTER TABLE posts ADD COLUMN tg_views INTEGER;
    ALTER TABLE posts ADD COLUMN tg_reactions TEXT;
    ALTER TABLE posts ADD COLUMN tg_media TEXT;
    CREATE TABLE tg_post_msgs (
        channel  INTEGER NOT NULL,
        msg_id   INTEGER NOT NULL,
        post_id  INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        grouped  INTEGER,                             -- the album it belongs to
        PRIMARY KEY (channel, msg_id)
    ) STRICT;
    CREATE INDEX tg_post_msgs_by_post ON tg_post_msgs(post_id);
    CREATE INDEX tg_post_msgs_by_album ON tg_post_msgs(channel, grouped);"""),
    # a channel's post in three languages: schools post kk/ru/en as separate posts (folded into one) or
    # write the translations as the channel in the post's comments; only without either, our AI (ai.py). i18n holds
    # the other languages, lang the source's (NULL: none yet), tr_by where they came from ('tg' official, 'ai');
    # tg_post_msgs.lang: the language a folded message gave its post (NULL: the post's own text)
    (73, """ALTER TABLE posts ADD COLUMN i18n TEXT;
    ALTER TABLE posts ADD COLUMN lang TEXT;
    ALTER TABLE posts ADD COLUMN tr_by TEXT;
    ALTER TABLE posts ADD COLUMN ai_tries INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE tg_post_msgs ADD COLUMN lang TEXT;"""),
    # PLAN 95: the clubs' rosters from DMP's Student Union sheet, each row waiting for its student:
    # joined at once when the Telegram username (or e-mail) AND the name match the KBTU account (roster.py), asked when
    # only the username does; claimed_by: "Yes, it's me" anyway, waiting for the club's President (or DMP); rejected_by:
    # declined by them, kept for the right person. users.city from it (hideable, deletable). A one-off until everyone
    # has signed up: dropped by hand later
    (74, """CREATE TABLE roster_pending (
        id         INTEGER PRIMARY KEY,
        key        TEXT NOT NULL UNIQUE,              -- the sheet's row, so a second load adds nothing
        org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        sheet      TEXT NOT NULL,
        position   TEXT,                              -- as written
        title      TEXT,                              -- the position as a club role's name (none for a plain member)
        role       TEXT NOT NULL CHECK (role IN ('member', 'head', 'vice', 'president')),
        dept       TEXT,
        full_name  TEXT,
        school     TEXT,
        year       TEXT,                              -- as written: 2, 23BD, 3rd year
        course     INTEGER,
        city       TEXT,
        phone      TEXT,                              -- +7XXXXXXXXXX
        tg         TEXT,                              -- lowercase, no @
        email      TEXT,                              -- lowercase
        rejected_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        claimed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,  -- "Yes, it's me" on another name: for the club to confirm
        created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX roster_by_tg ON roster_pending(tg);
    CREATE INDEX roster_by_email ON roster_pending(email);
    CREATE INDEX roster_by_org ON roster_pending(org_id);
    CREATE TABLE roster_toasts (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        org_id  INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
        title   TEXT,
        at      INTEGER NOT NULL
    ) STRICT;
    ALTER TABLE users ADD COLUMN city TEXT;
    ALTER TABLE users ADD COLUMN city_hidden INTEGER NOT NULL DEFAULT 0;"""),
    # what the report queue took down and an undo needs: an album photo's row, a profile's nick, photo
    # and "about me", kept 30 days with the file (it counts as shown, logic._drop_unused), then gone from disk too
    (75, """CREATE TABLE takedowns (
        id        INTEGER PRIMARY KEY,
        target    TEXT NOT NULL CHECK (target IN ('photo', 'user')),
        target_id INTEGER NOT NULL,
        user_id   INTEGER REFERENCES users(id) ON DELETE CASCADE,   -- whose it was: the photo's uploader, the person
        data      TEXT NOT NULL,                                     -- JSON: the album row / nick, bio, avatar
        file_id   INTEGER REFERENCES files(id),                      -- the picture kept for the undo
        at        INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX takedowns_by_target ON takedowns(target, target_id);"""),
    # F1 find people (forum, PLAN): a shared skills catalog, requests, contact by double opt-in, blocks, pings
    (76, """CREATE TABLE skills (
        id         INTEGER PRIMARY KEY,
        name       TEXT NOT NULL UNIQUE,                  -- normalised: lowercase, single spaces
        approved   INTEGER NOT NULL DEFAULT 0,            -- a moderator's yes; else public at 3 people (forum.PUBLIC_AT)
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at INTEGER NOT NULL,
        used_at    INTEGER NOT NULL                       -- last added to someone or a request: unused 30 days, out of suggestions
    ) STRICT;
    CREATE TABLE user_skills (
        user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, skill_id)
    ) STRICT;
    CREATE INDEX user_skills_by_skill ON user_skills(skill_id);
    CREATE TABLE asks (
        id         INTEGER PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind       TEXT NOT NULL CHECK (kind IN ('project', 'help')),
        title      TEXT NOT NULL,
        body       TEXT NOT NULL DEFAULT '',
        status     TEXT NOT NULL CHECK (status IN ('live', 'held', 'hidden', 'closed')),
        why        TEXT,                                  -- held / hidden: what the author is told
        found      INTEGER,                               -- closed: found someone through the app (1), elsewhere (0)
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX asks_live ON asks(status, expires_at);
    CREATE TABLE ask_skills (
        ask_id   INTEGER NOT NULL REFERENCES asks(id) ON DELETE CASCADE,
        skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
        PRIMARY KEY (ask_id, skill_id)
    ) STRICT;
    CREATE TABLE contacts (                               -- "I can help" / "write to them": nothing shared until accepted
        id         INTEGER PRIMARY KEY,
        from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        ask_id     INTEGER REFERENCES asks(id) ON DELETE CASCADE,
        status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
        created_at INTEGER NOT NULL,
        decided_at INTEGER
    ) STRICT;
    CREATE UNIQUE INDEX one_contact ON contacts(from_id, to_id, COALESCE(ask_id, 0));
    CREATE TABLE blocks (
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (user_id, blocked_id)
    ) STRICT;
    CREATE TABLE ask_pings (
        ask_id  INTEGER NOT NULL REFERENCES asks(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        at      INTEGER NOT NULL,
        PRIMARY KEY (ask_id, user_id)
    ) STRICT;
    CREATE INDEX ask_pings_by_user ON ask_pings(user_id, at);
    ALTER TABLE users ADD COLUMN open_projects INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN ask_pings INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE reports3 (
        id INTEGER PRIMARY KEY,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        target TEXT NOT NULL CHECK (target IN ('post', 'comment', 'event', 'user', 'org', 'photo', 'ask')),
        target_id INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK (reason IN ('spam', 'insult', 'danger', 'other')),
        note TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
        created_at INTEGER NOT NULL,
        resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        resolved_at INTEGER
    ) STRICT;
    INSERT INTO reports3 SELECT id, reporter_id, target, target_id, reason, note, status, created_at, resolved_by, resolved_at FROM reports;
    DROP TABLE reports;
    ALTER TABLE reports3 RENAME TO reports;
    CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id) WHERE status = 'open';
    INSERT INTO skills (name, approved, created_at, used_at) SELECT value, 1, CAST(strftime('%s', 'now') AS INTEGER),
        CAST(strftime('%s', 'now') AS INTEGER) FROM json_each('["ios", "android", "web", "backend", "ml", "data", "ui design", "graphic design", "3d", "photo", "video", "editing", "texts", "translation", "smm", "music", "events"]');"""),
    # referrals (PLAN): who brought me, by their invite link (r_<badge code>); the first link wins.
    # 77, not 76: 76 is the forum (sower4d/forum-people), to be merged first
    (77, """ALTER TABLE users ADD COLUMN referred_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    CREATE INDEX users_by_referrer ON users(referred_by) WHERE referred_by IS NOT NULL;"""),
    # our copy of the Telegram photo (bot._userpics): t.me took ~1 s per open; src = the t.me URL it was made from
    (78, """ALTER TABLE users ADD COLUMN tg_photo_path TEXT;
    ALTER TABLE users ADD COLUMN tg_photo_src TEXT;"""),
    # check-in by a QR on a big screen (checkin.py): a session (its PIN hashed), the scans, the organizers' expected list
    (79, """CREATE TABLE qr_sessions (
      id         INTEGER PRIMARY KEY,
      title      TEXT NOT NULL,
      pin_hash   TEXT NOT NULL UNIQUE,
      started_at INTEGER,
      ended_at   INTEGER,
      created_at INTEGER NOT NULL
    ) STRICT;
    CREATE TABLE qr_marks (
      session_id INTEGER NOT NULL REFERENCES qr_sessions(id) ON DELETE CASCADE,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      scanned_at INTEGER NOT NULL,
      done_at    INTEGER,
      PRIMARY KEY (session_id, user_id)
    ) STRICT;
    CREATE TABLE qr_expected (
      session_id INTEGER NOT NULL REFERENCES qr_sessions(id) ON DELETE CASCADE,
      email      TEXT NOT NULL,
      full_name  TEXT NOT NULL,
      student_id TEXT,
      school     TEXT,
      course     INTEGER,
      phone      TEXT,
      tg         TEXT,
      extra      TEXT NOT NULL DEFAULT '{}',
      PRIMARY KEY (session_id, email)
    ) STRICT;
    CREATE INDEX qr_expected_by_email ON qr_expected(email);"""),
    # a partner's event a club posts (Oct 29, the Incubator's Halloween party): "With <host>" under the club, a link out
    # (external_url) instead of tickets, no ping to followers, out of the club's numbers and achievements
    (80, "ALTER TABLE events ADD COLUMN guest_host TEXT;"),
    # /show paired from an organizer's phone instead of a PIN (checkin.py): a session belongs to a club, a screen is
    # its pairing code + the hash of a secret only that browser holds
    (81, """ALTER TABLE qr_sessions ADD COLUMN org_id INTEGER REFERENCES orgs(id) ON DELETE SET NULL;
    CREATE TABLE qr_screens (
      code       TEXT PRIMARY KEY,
      secret     TEXT NOT NULL UNIQUE,
      session_id INTEGER REFERENCES qr_sessions(id) ON DELETE CASCADE,
      paired_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX qr_screens_by_session ON qr_screens(session_id);"""),
    # a check-in session made from an event in the app (its organizer's "Check-in screen"): one per event, its done
    # scans are that event's check-ins
    (82, """ALTER TABLE qr_sessions ADD COLUMN event_id INTEGER REFERENCES events(id) ON DELETE SET NULL;
    CREATE UNIQUE INDEX qr_sessions_by_event ON qr_sessions(event_id) WHERE event_id IS NOT NULL;"""),
    # the student forum (logic/threads.py, Oct 30): threads, replies, "I'm in"; anonymous ones keep their author for
    # the admin's audited reveal only. Reports learn 'thread' and 'reply' (the table rebuilt: a CHECK can't be altered)
    (83, """CREATE TABLE threads (
      id         INTEGER PRIMARY KEY,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      topic      TEXT NOT NULL CHECK (topic IN ('thing', 'go', 'help', 'vol', 'talk')),
      body       TEXT NOT NULL CHECK (status = 'gone' OR length(body) BETWEEN 2 AND 1000),
      anon       INTEGER NOT NULL DEFAULT 0,
      status     TEXT NOT NULL CHECK (status IN ('live', 'held', 'hidden', 'gone')),  -- gone: its author deleted it (words wiped; still counts toward the allowance)
      why        TEXT,                                  -- held / hidden: 'ai', 'check' (no AI answer), 'reports', 'moderator'
      created_at INTEGER NOT NULL,
      bumped_at  INTEGER NOT NULL,                      -- the last live reply: the feed's order
      expires_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX threads_feed ON threads(status, bumped_at);
    CREATE INDEX threads_by_user ON threads(user_id, created_at);
    CREATE TABLE thread_replies (
      id         INTEGER PRIMARY KEY,
      thread_id  INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      body       TEXT NOT NULL CHECK (status = 'gone' OR length(body) BETWEEN 1 AND 500),
      anon       INTEGER NOT NULL DEFAULT 0,
      status     TEXT NOT NULL CHECK (status IN ('live', 'held', 'hidden', 'gone')),
      why        TEXT,
      created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX thread_replies_by_thread ON thread_replies(thread_id, id);
    CREATE INDEX thread_replies_by_user ON thread_replies(user_id, created_at);
    CREATE TABLE thread_joins (
      thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
      user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      at        INTEGER NOT NULL,
      PRIMARY KEY (thread_id, user_id)
    ) STRICT;
    CREATE TABLE reports4 (
        id INTEGER PRIMARY KEY,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        target TEXT NOT NULL CHECK (target IN ('post', 'comment', 'event', 'user', 'org', 'photo', 'ask', 'thread', 'reply')),
        target_id INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK (reason IN ('spam', 'insult', 'danger', 'other')),
        note TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
        created_at INTEGER NOT NULL,
        resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        resolved_at INTEGER
    ) STRICT;
    INSERT INTO reports4 SELECT id, reporter_id, target, target_id, reason, note, status, created_at, resolved_by, resolved_at FROM reports;
    DROP TABLE reports;
    ALTER TABLE reports4 RENAME TO reports;
    CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id) WHERE status = 'open';"""),
    # the bot's "someone answered your forum thread" has its own switch in Settings
    (84, "ALTER TABLE users ADD COLUMN n_forum INTEGER NOT NULL DEFAULT 1;"),
    # /show's pairing codes per address (its hash): one address can't take every free code and lock all screens out
    (85, "ALTER TABLE qr_screens ADD COLUMN ip TEXT; CREATE INDEX qr_screens_by_ip ON qr_screens(ip) WHERE session_id IS NULL;"),
    # an event's own questions at sign-up (Oct 30, an organizer's ask): JSON [{label, kind text|choice, options, required}];
    # the answers on the registration, JSON [{q, a}] (the question's words as they were), wiped 30 days after the event
    (86, "ALTER TABLE events ADD COLUMN questions TEXT; ALTER TABLE registrations ADD COLUMN answers TEXT;"),
    # "something's wrong here" on the map (owner, Oct 29: marking the map's flaws in the app, not by screenshots): the
    # map version and floor, the spot (the sheet's fraction and the 2023 plan's units), a line of text
    (87, """CREATE TABLE map_flaws (
      id         INTEGER PRIMARY KEY,
      user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
      ver        TEXT NOT NULL CHECK (ver IN ('main', 'old', 'kbtu')),
      floor      INTEGER NOT NULL CHECK (floor BETWEEN 0 AND 5),
      u          REAL NOT NULL, v REAL NOT NULL, px REAL, py REAL,
      body       TEXT NOT NULL CHECK (length(body) BETWEEN 2 AND 300),
      created_at INTEGER NOT NULL,
      done_at    INTEGER
    ) STRICT;
    CREATE INDEX map_flaws_open ON map_flaws(done_at, created_at);"""),
    # the assistant (logic/assistant.py): a count per day, never the questions
    (88, """CREATE TABLE assist_uses (
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      at      INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX assist_uses_by_user ON assist_uses(user_id, at);"""),
    # the check-in's way out (owner, Oct 30: who left and when, for the initiation's volunteers): the session's phase,
    # 'in' or 'out', and the last time each person scanned out
    (89, "ALTER TABLE qr_sessions ADD COLUMN phase TEXT NOT NULL DEFAULT 'in' CHECK (phase IN ('in', 'out')); ALTER TABLE qr_marks ADD COLUMN left_at INTEGER;"),
    # links (r_, ev_) get their own code: they're posted in chats, and the badge's secret was in them (review, Oct 30). The
    # links already out keep working (they carry today's code, now the link code); every badge gets a new secret
    (90, """ALTER TABLE users ADD COLUMN link_code TEXT;
    UPDATE users SET link_code = qr_code, qr_code = NULL WHERE qr_code IS NOT NULL;
    CREATE UNIQUE INDEX users_link ON users(link_code);"""),
    # the assistant's campus facts, kept current by the admin and moderators (owner, Oct 30: the list in the code is likely
    # outdated). A room as the plan writes it, or `location` in words; one dean's office per school. Seeded from that list:
    # its English names (the Russian and Kazakh unknown), never checked (verified_at NULL); the codes are the map's spots
    (91, """CREATE TABLE campus_places (
      id          INTEGER PRIMARY KEY,
      kind        TEXT NOT NULL CHECK (kind IN ('place', 'dean', 'office')),
      code        TEXT NOT NULL UNIQUE,
      name_en     TEXT NOT NULL,
      name_ru     TEXT,
      name_kk     TEXT,
      aliases     TEXT,
      room        TEXT,
      location    TEXT,
      school      TEXT,
      verified_at INTEGER,
      updated_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
      updated_at  INTEGER NOT NULL
    ) STRICT;
    CREATE UNIQUE INDEX campus_places_dean ON campus_places(school) WHERE kind = 'dean';
    INSERT INTO campus_places (kind, code, name_en, room, location, school, updated_at)
      SELECT *, CAST(strftime('%s', 'now') AS INTEGER) FROM (VALUES
        ('place', 'canteen', 'Canteen', NULL, 'the basement, floor 0', NULL), ('place', 'library', 'Library', '158', NULL, NULL),
        ('place', 'career', 'Career Center', '152', NULL, NULL), ('place', 'students', 'Student services', '155', NULL, NULL),
        ('place', 'cowork', 'Halyk Co-working', NULL, 'floor 1, the middle block', NULL),
        ('place', 'kunaev', 'Kunaev auditorium', '400a', NULL, NULL), ('place', 'farabi', 'Al-Farabi hall', '470', NULL, NULL),
        ('place', 'indep', 'Independence hall', NULL, 'floor 2', NULL), ('place', 'gamedev', 'Gamedev lab', '47', NULL, NULL),
        ('place', 'honeywell', 'Honeywell lab', '140', NULL, NULL), ('office', 'security', 'Security', '250a', NULL, NULL),
        ('office', 'dispatch', 'Dispatcher', '1', NULL, NULL), ('office', 'rector', 'Rector', '466', NULL, NULL),
        ('office', 'vrScience', 'Vice-rector for science', '415', NULL, NULL),
        ('office', 'vrSocial', 'Vice-rector for social affairs', '472', NULL, NULL),
        ('office', 'legal', 'Legal department', '503', NULL, NULL), ('office', 'accounting', 'Accounting', '523', NULL, NULL),
        ('dean', 'site', 'School of IT and Engineering', '180', NULL, 'SITE'),
        ('dean', 'energy', 'School of Energy and Petroleum Industry', '356', NULL, 'SEOGI'),
        ('dean', 'marine', 'Kazakhstan Maritime Academy', '255', NULL, 'KMA'));"""),
    # a club role's name in Kazakh and English (`name` stays the required one, the fallback)
    (92, "ALTER TABLE org_roles ADD COLUMN name_kk TEXT; ALTER TABLE org_roles ADD COLUMN name_en TEXT;"),
    # the assistant's feedback (review, Oct 31), none of it tied to a person: the model's short topic of a question it
    # couldn't answer and the thumbs up/down on an answer (with its topic); a question and answer a student chose to send
    # after a thumbs down (all by UTC day, 30 days: assistant.sweep); how many times a week the helplines were shown
    (93, """CREATE TABLE assist_marks (
      day   INTEGER NOT NULL,
      kind  TEXT NOT NULL CHECK (kind IN ('unknown', 'up', 'down')),
      topic TEXT NOT NULL
    ) STRICT;
    CREATE INDEX assist_marks_day ON assist_marks(day);
    CREATE TABLE assist_sent (
      id  INTEGER PRIMARY KEY,
      day INTEGER NOT NULL,
      q   TEXT NOT NULL,
      a   TEXT NOT NULL
    ) STRICT;
    CREATE TABLE assist_care (
      week INTEGER PRIMARY KEY,
      n    INTEGER NOT NULL
    ) STRICT;"""),
    # an answer's one-time nonce once voted on (one vote an answer; a sent pair needs its thumbs down first); no user id,
    # 2 days (assistant.sweep)
    (94, """CREATE TABLE assist_votes (
      nonce TEXT PRIMARY KEY,
      day   INTEGER NOT NULL,
      kind  TEXT NOT NULL CHECK (kind IN ('up', 'down', 'sent'))
    ) STRICT;"""),
    # the freshmen list of the Oct 31 2026 initiation (admin prefill-import), keyed by the KBTU email: shown only to
    # that student in their own sign-up form, gone when they link (account.ms_link) or delete the account
    (95, """CREATE TABLE prefill (
      email       TEXT PRIMARY KEY,
      student_id  TEXT NOT NULL,
      last_name   TEXT,
      first_name  TEXT,
      middle_name TEXT,
      school      TEXT,
      phone       TEXT,
      came        INTEGER NOT NULL DEFAULT 0 CHECK (came IN (0, 1))
    ) STRICT;"""),
    # Settings → My data: the fields a student corrected themselves (each once: student_id, last_name, first_name,
    # middle_name, comma-separated); the old values are in audit_log (identity_fix). Gone with the row
    (96, "ALTER TABLE students ADD COLUMN fixed TEXT NOT NULL DEFAULT '';"),
    # the name in Latin as KBTU's directory (Microsoft's displayName, account.latin_from_ms) or the freshmen list spells it,
    # or as the student typed it in My data; never generated (review latin-names-review.md). The English UI and the exports
    (97, """ALTER TABLE students ADD COLUMN last_lat TEXT; ALTER TABLE students ADD COLUMN first_lat TEXT;
    ALTER TABLE students ADD COLUMN middle_lat TEXT;"""),
    # the rest of that freshmen list (admin prefill-rest): rows the main import couldn't key by one KBTU mail and one ID.
    # Matched at ms_link by the KBTU mail or a valid ID, and the name; never fills the ID. raw_id: as typed, the owner's
    # alone. Gone when used or with the account (account.delete_me)
    (98, """CREATE TABLE prefill_rest (
      id          INTEGER PRIMARY KEY,
      email       TEXT,
      student_id  TEXT,
      raw_id      TEXT,
      last_name   TEXT,
      first_name  TEXT,
      middle_name TEXT,
      school      TEXT,
      phone       TEXT,
      came        INTEGER NOT NULL DEFAULT 0 CHECK (came IN (0, 1))
    ) STRICT;
    CREATE INDEX prefill_rest_email ON prefill_rest(email);
    CREATE INDEX prefill_rest_sid ON prefill_rest(student_id);"""),
    # an award link many may open until it expires, one award each (admin claim new: the volunteers' badge in their chat)
    (99, "ALTER TABLE grant_links ADD COLUMN multi INTEGER NOT NULL DEFAULT 0;"),
    # the forum channel's comments (FORUM_GROUP, logic/tgcomments.py): a stranger's deleted comment kept for him alone
    # an hour; strangers warned once, then banned (90 days); reported comments with each reporter's snapshot (30 days);
    # those whose /report a moderator closed for abuse (until an admin reopens it or the account goes)
    (100, """CREATE TABLE tgc_saved (
      tg_id INTEGER PRIMARY KEY,
      body  TEXT NOT NULL,
      link  TEXT,
      at    INTEGER NOT NULL
    ) STRICT;
    CREATE TABLE tgc_strangers (
      tg_id     INTEGER PRIMARY KEY,
      seen_at   INTEGER NOT NULL,
      warned_at INTEGER,
      banned_at INTEGER
    ) STRICT;
    CREATE INDEX tgc_strangers_seen ON tgc_strangers(seen_at);
    CREATE TABLE tgc_comments (
      id         INTEGER PRIMARY KEY,
      chat_id    INTEGER NOT NULL,
      msg_id     INTEGER NOT NULL,
      author_id  INTEGER REFERENCES users(id) ON DELETE CASCADE,
      author_tg  INTEGER NOT NULL,
      body       TEXT NOT NULL,                         -- the latest text seen (a report's snapshot, an edit)
      link       TEXT,
      status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'queued', 'deleting', 'deleted', 'kept', 'restored')),
      ai         TEXT CHECK (ai IN ('ok', 'flag', 'none')),
      ai_hash    TEXT,                                  -- the text the AI last looked at: the same text isn't sent again
      created_at INTEGER NOT NULL,
      decided_at INTEGER,
      review     INTEGER NOT NULL DEFAULT 0 CHECK (review IN (0, 1)),  -- deleted on the reports and the AI: a moderator confirms or restores
      shown      INTEGER NOT NULL DEFAULT 0 CHECK (shown IN (0, 1)),   -- deleted, and its author (whom the bot can't write to) saw it in the app
      rule       TEXT CHECK (rule IN ('spam', 'insult', 'danger', 'other')),  -- the rule it broke: the AI's guess, then the moderator's word
      dm_id      INTEGER,                               -- the bot's message to its author: a verdict edits it in place
      UNIQUE (chat_id, msg_id)
    ) STRICT;
    CREATE TABLE tgc_reports (
      comment_id  INTEGER NOT NULL REFERENCES tgc_comments(id) ON DELETE CASCADE,
      reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      body        TEXT NOT NULL,                        -- the text as this reporter saw it
      at          INTEGER NOT NULL,
      outcome     TEXT CHECK (outcome IN ('confirmed', 'overturned', 'abuse')),
      PRIMARY KEY (comment_id, reporter_id)
    ) STRICT;
    CREATE INDEX tgc_reports_by ON tgc_reports(reporter_id, at);
    CREATE TABLE tgc_closed (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      at      INTEGER NOT NULL,
      by_id   INTEGER REFERENCES users(id) ON DELETE SET NULL
    ) STRICT;"""),
    # the clause of the terms' section 3 a removed Telegram comment broke (tgcomments.RULES); rule stays for old rows
    (101, """ALTER TABLE tgc_comments ADD COLUMN clause TEXT CHECK (clause IN ('abuse', 'fake', 'spam', 'pdata', 'disrupt', 'other'));
    UPDATE tgc_comments SET clause = CASE rule WHEN 'spam' THEN 'spam' WHEN 'other' THEN 'other' ELSE 'abuse' END WHERE rule IS NOT NULL;"""),
    # the forum channel (FORUM_CHANNEL, logic/fchannel.py, Nov 1): a student's post, published by the bot after the AI's
    # or a moderator's yes; the author kept for the owner's audited reveal while the post exists. tg_unpost: channel
    # messages to take down, no foreign key and nothing personal, so a deleted account's posts still leave the channel
    (102, """CREATE TABLE fchan_posts (
      id         INTEGER PRIMARY KEY,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      body       TEXT NOT NULL CHECK (status = 'gone' OR length(body) BETWEEN 2 AND 1000),
      anon       INTEGER NOT NULL DEFAULT 0,
      status     TEXT NOT NULL CHECK (status IN ('held', 'live', 'hidden', 'gone')),  -- gone: the author deleted it (words wiped; still counts toward the day)
      why        TEXT,                                  -- held: 'check' (no AI answer yet), 'ai', 'person', 'busy'; hidden: 'moderator'
      tg_msg     INTEGER,                               -- the channel message, once sent
      created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX fchan_posts_by_user ON fchan_posts(user_id, created_at);
    CREATE INDEX fchan_posts_by_status ON fchan_posts(status, id);
    CREATE TABLE tg_unpost (
      msg_id INTEGER PRIMARY KEY,
      why    TEXT NOT NULL CHECK (why IN ('author', 'moderator')),
      at     INTEGER NOT NULL
    ) STRICT;"""),
    # the old student forum (threads.py) is replaced by the channel (owner, Nov 1: clean it up): its threads, replies,
    # "I'm in" marks, reports and the bot's unsent notes about them go
    (103, """DELETE FROM thread_joins; DELETE FROM thread_replies; DELETE FROM threads;
    DELETE FROM reports WHERE target IN ('thread', 'reply');
    DELETE FROM bot_outbox WHERE kind = 'thread_reply';"""),
    # (cloud review, Nov 1) a replaced receipt's fingerprint: the duplicate check still sees it, and it counts toward the
    # replacements' cap (seats.RECEIPT_TRIES); its picture leaves the disk. tgc_undel: a deleted account's comments
    # still to come out of the discussion group (deleting, or in the moderators' queue): ids only, nothing personal
    (104, """CREATE TABLE IF NOT EXISTS receipt_replaced (
      registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
      sha256          TEXT NOT NULL,
      receipt_no      TEXT,
      at              INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS receipt_replaced_by_reg ON receipt_replaced(registration_id);
    CREATE INDEX IF NOT EXISTS receipt_replaced_by_sha ON receipt_replaced(sha256);
    CREATE INDEX IF NOT EXISTS receipt_replaced_by_no ON receipt_replaced(receipt_no) WHERE receipt_no IS NOT NULL;
    CREATE TABLE IF NOT EXISTS tgc_undel (
      chat_id INTEGER NOT NULL,
      msg_id  INTEGER NOT NULL,
      at      INTEGER NOT NULL,
      PRIMARY KEY (chat_id, msg_id)
    ) STRICT;"""),
    # (Nov 2) the bot's first comment under a forum channel post (the rules, a button to the post in the app): the
    # channel message it was written under, once per message (the posts already out had their button: none for them),
    # and its id in the group, the Forum tab's link into the comments. comments: the students' comments the bot saw
    # under the post (Telegram's Bot API has no count), for the tab's Comments row
    (105, """ALTER TABLE fchan_posts ADD COLUMN rules_for INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN rules_msg INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN comments INTEGER NOT NULL DEFAULT 0;
    -- a signed post's signature as written (the nick if the author had one, else the short name); NULL: anonymous, or
    -- older than this (signed with the short name)
    ALTER TABLE fchan_posts ADD COLUMN sign TEXT;
    UPDATE fchan_posts SET rules_for = tg_msg WHERE tg_msg > 0;
    -- fchcopy:<channel message> = its copy in the group, the forum channel's alone (tgc.gate checks the sender); until
    -- now only the group's own channel's copies were mapped (tgcpost:), and that was the forum channel
    INSERT OR IGNORE INTO meta (key, value) SELECT 'fchcopy:' || substr(value, instr(value, ' ') + 1), substr(key, 9)
      FROM meta WHERE key LIKE 'tgcpost:%';"""),
    # (Nov 2) the chats directory by what a chat is for (owner: study, reviews, admission, schools and courses, clubs,
    # hobbies and fun); the AI sorts each chat by its public title and description (logic/chatlist.py sort_next), staff
    # correct it in Admin. section NULL: not sorted yet; section_ai 1: the AI's, no one checked; section_try: the last
    # time the AI was asked (a failed ask waits an hour)
    (106, """ALTER TABLE chats ADD COLUMN section TEXT CHECK (section IN ('study', 'reviews', 'admission', 'schools', 'clubs', 'fun'));
    ALTER TABLE chats ADD COLUMN section_ai INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE chats ADD COLUMN section_try INTEGER;
    -- everyone who suggested a chat while it waited, each told once when staff approve it (chats.added_by: the first)
    CREATE TABLE chat_asks (
      chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      PRIMARY KEY (chat_id, user_id)
    ) STRICT;
    INSERT INTO chat_asks (chat_id, user_id) SELECT id, added_by FROM chats WHERE status = 'pending' AND added_by IS NOT NULL;"""),
    # (Nov 2) a forum post's card mirrors Telegram: the faces of the app's students who commented (one row per comment
    # the bot saw, by its id in the discussion group: a comment seen twice counts once) and the channel post's
    # reactions (Telegram's message_reaction_count, as {"👍": 3, "custom:<id>": 1}). A comment taken out of Telegram
    # (a report's deletion) leaves the count and the faces, and comes back with a moderator's "keep": the trigger
    # follows tgc_comments' status, so every path that changes it is covered (its 30-day sweep deletes, never updates).
    # ponytail: the trigger matches msg_id alone, without chat_id: one discussion group today (FORUM_GROUP); a second
    # group or a new one reusing ids needs chat_id in fchan_comments and in the match
    (107, """ALTER TABLE fchan_posts ADD COLUMN reactions TEXT;
    CREATE TABLE fchan_comments (
      msg_id  INTEGER PRIMARY KEY,
      post_id INTEGER NOT NULL REFERENCES fchan_posts(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      at      INTEGER NOT NULL,
      gone    INTEGER NOT NULL DEFAULT 0
    ) STRICT;
    CREATE INDEX fchan_comments_by_post ON fchan_comments(post_id, at);
    CREATE INDEX fchan_comments_by_user ON fchan_comments(user_id);
    CREATE TRIGGER fchan_comment_gone AFTER UPDATE OF status ON tgc_comments
      WHEN (NEW.status IN ('deleting', 'deleted', 'restored')) != (OLD.status IN ('deleting', 'deleted', 'restored'))
    BEGIN
      UPDATE fchan_posts SET comments = MAX(0, comments + CASE WHEN NEW.status IN ('deleting', 'deleted', 'restored') THEN -1 ELSE 1 END)
        WHERE id = (SELECT post_id FROM fchan_comments WHERE msg_id = NEW.msg_id AND gone = (NEW.status NOT IN ('deleting', 'deleted', 'restored')));
      UPDATE fchan_comments SET gone = (NEW.status IN ('deleting', 'deleted', 'restored')) WHERE msg_id = NEW.msg_id;
    END;"""),
    # (Nov 2) a round's own "what's next" (casting audit: "come in person, 3-12 Nov, Kazybek bi, 1st floor"), the club's
    # words shown in the app under the steps like its description; the bot keeps its template
    (108, "ALTER TABLE rounds ADD COLUMN next_text TEXT NOT NULL DEFAULT '' CHECK (length(next_text) <= 300);"),
    # (Nov 2) the postman's due query (bot._due) every 2 s walked every failed row: only the waiting ones indexed
    (109, "CREATE INDEX IF NOT EXISTS outbox_todo ON bot_outbox(send_after, id) WHERE sent_at IS NULL AND error IS NULL;"),
    # (Nov 2, review 12) my join requests on every club list; the feed's pinned-first order; the Afisha's date range
    (110, """CREATE INDEX IF NOT EXISTS join_requests_by_user ON join_requests(user_id);
    CREATE INDEX IF NOT EXISTS posts_feed ON posts(audience, pinned, created_at);
    CREATE INDEX IF NOT EXISTS events_by_start ON events(starts_at);"""),
    # (Nov 2) a club's member link for the whole team (logic.team_link): many join by it as plain members, 7 days, one per club
    (111, "ALTER TABLE org_invites ADD COLUMN multi INTEGER NOT NULL DEFAULT 0;"),
    # (Nov 2) a frame drawn over my photo on the lanyard, picked apart from the lanyard itself (logic.FRAMES)
    (112, "ALTER TABLE users ADD COLUMN frame TEXT;"),
    # the stranger's message his warning was for: the same update again after a restart is not a second comment
    (113, "ALTER TABLE tgc_strangers ADD COLUMN warned_msg INTEGER;"),
    # (Nov 2) a forum channel post reported from the feed ('fpost', logic/moderation.py): the CHECK takes the new kind.
    # Rebuilt as 106 did: nothing references reports, so no cascade can reach a child
    (114, """CREATE TABLE reports5 (
        id INTEGER PRIMARY KEY,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        target TEXT NOT NULL CHECK (target IN ('post', 'comment', 'event', 'user', 'org', 'photo', 'ask', 'thread', 'reply', 'fpost')),
        target_id INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK (reason IN ('spam', 'insult', 'danger', 'other')),
        note TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
        created_at INTEGER NOT NULL,
        resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        resolved_at INTEGER
    ) STRICT;
    INSERT INTO reports5 SELECT id, reporter_id, target, target_id, reason, note, status, created_at, resolved_by, resolved_at FROM reports;
    DROP TABLE reports;
    ALTER TABLE reports5 RENAME TO reports;
    CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id) WHERE status = 'open';"""),
    # "Can add me as a friend" (owner, Nov 2): off, nobody can send me a request; friends and waiting requests stay
    (115, "ALTER TABLE users ADD COLUMN can_friend INTEGER NOT NULL DEFAULT 1;"),
    # the school before its one correction ({"school": ...}): going back to it is free, once
    # (owner, Nov 3: a mis-tap cost the only change and every student wrote to support)
    (116, "ALTER TABLE students ADD COLUMN once_was TEXT NOT NULL DEFAULT '{}';"),
    # (Nov 3, .claude/reports/anon-reply/review.md) an anonymous post's author answers in its comments through the bot.
    # No user_id: the author is reached through the post alone (reveal, account deletion follow it), and the replies go
    # with their post. comment_msg: the comment answered (fchan_comments.msg_id), NULL for the thread. tg_msg as the
    # posts': NULL not sent, 0 on its way, else the bot's message in the group; drop_at: when it leaves the group
    (117, """CREATE TABLE fchan_replies (
      id          INTEGER PRIMARY KEY,
      post_id     INTEGER NOT NULL REFERENCES fchan_posts(id) ON DELETE CASCADE,
      comment_msg INTEGER,
      body        TEXT NOT NULL CHECK (status = 'gone' OR length(body) BETWEEN 2 AND 1000),
      status      TEXT NOT NULL CHECK (status IN ('held', 'live', 'hidden', 'gone')),
      why         TEXT,
      tg_msg      INTEGER,
      send_at     INTEGER,
      drop_at     INTEGER,
      created_at  INTEGER NOT NULL
    ) STRICT;
    -- /report on a reply in the group: who reported, once each; gone with the reply and with the reporter's account
    CREATE TABLE fchan_reply_reports (
      reply_id INTEGER NOT NULL REFERENCES fchan_replies(id) ON DELETE CASCADE,
      user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      at       INTEGER NOT NULL,
      PRIMARY KEY (reply_id, user_id)
    ) STRICT;
    CREATE INDEX fchan_reply_reports_by_user ON fchan_reply_reports(user_id);
    CREATE INDEX fchan_replies_by_post ON fchan_replies(post_id, created_at);
    CREATE INDEX fchan_replies_by_msg ON fchan_replies(tg_msg) WHERE tg_msg > 0;
    CREATE INDEX fchan_replies_todo ON fchan_replies(status, send_at) WHERE tg_msg IS NULL;"""),
    # Admin → Awards (Nov 3): a grant's batch, undone at once: a scanner run ('s_…'), a link's people ('l_<token>'), a
    # check-in session's ('q<sid>_<ts>'); a link's cap of people (NULL: no cap)
    (118, """ALTER TABLE achievement_grants ADD COLUMN batch TEXT;
    CREATE INDEX grants_by_batch ON achievement_grants(batch) WHERE batch IS NOT NULL;
    ALTER TABLE grant_links ADD COLUMN max_uses INTEGER;
    -- who used a link, once each: its cap counts these, so an undo or a deleted account never frees a slot (user_id
    -- goes NULL with the account and the row stays)
    CREATE TABLE grant_link_uses (
      id      INTEGER PRIMARY KEY,
      token   TEXT NOT NULL REFERENCES grant_links(token) ON DELETE CASCADE,
      user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      at      INTEGER NOT NULL,
      UNIQUE (token, user_id)
    ) STRICT;
    CREATE INDEX grant_link_uses_by_user ON grant_link_uses(user_id);"""),
    # Admin → Inbox (Nov 3): decided() and Undo read a thing's newest line, Done the last 30 days
    (119, """CREATE INDEX IF NOT EXISTS audit_by_target ON audit_log(target, id);
    CREATE INDEX IF NOT EXISTS audit_by_at ON audit_log(at);"""),
    # late sign-up (Nov 3): a free uncapped public event keeps "Going" open from its start until its end
    (120, "ALTER TABLE events ADD COLUMN late_signup INTEGER NOT NULL DEFAULT 0;"),
    # an anonymous post's random nick (Nov 3, .claude/reports/anon-nicks-review.md): texts.NICK_ADJ / NICK_NOUN indexes,
    # drawn with secrets at the reserve; NULL on posts from before (signed "Anon")
    (121, """ALTER TABLE fchan_posts ADD COLUMN nick_a INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN nick_n INTEGER;"""),
    # co-hosted events (Nov 3, "Crystal & JCC do an Anime Quiz together"): one other club of the app, invited by the
    # host, shown once its Vice+ accepts (logic/cohosts.py; events.co_org_id was never written and stays unused).
    # A declined row stays, so the same club isn't asked twice for one event; ending one deletes it.
    (122, """CREATE TABLE event_cohosts (
      event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
      invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at INTEGER NOT NULL,
      decided_at INTEGER,
      PRIMARY KEY (event_id, org_id)
    ) STRICT;
    CREATE UNIQUE INDEX one_cohost ON event_cohosts(event_id) WHERE status != 'declined';  -- ponytail: one co-host, more later
    CREATE INDEX cohosts_by_org ON event_cohosts(org_id, status);"""),
    # a forum post the AI refused (noise, an ad) that its author sent to a moderator (fchannel.appeal, Nov 4): when, for
    # the day's three; explained: the AI's reason for a refusal was asked (once a post or reply: ai.explain); refused: a
    # hash of the refused words (they're wiped), so the appeal and the reason are only ever about the words the AI read
    (123, """ALTER TABLE fchan_posts ADD COLUMN appealed_at INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN refused TEXT;
    ALTER TABLE fchan_posts ADD COLUMN explained INTEGER;
    ALTER TABLE fchan_replies ADD COLUMN explained INTEGER;"""),
    # the AI's reason (ai.explain's validated sentence) kept on the row, so a moderator deciding on a held or appealed
    # post or reply reads why the AI stopped it (owner, Nov 4: the Admin queue's reason line); goes with the row
    (124, """ALTER TABLE fchan_posts ADD COLUMN ai_reason TEXT;
    ALTER TABLE fchan_replies ADD COLUMN ai_reason TEXT;"""),
    # the path to the official ✓ (Nov 4): a student initiative that did the five steps asks the admin (logic/clubs.py,
    # official_path). Who asked and who decided are in the audit log; a no's reason the club reads in Studio
    (125, """CREATE TABLE official_requests (
      id         INTEGER PRIMARY KEY,
      org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
      reason     TEXT CHECK (length(reason) <= 300),
      created_at INTEGER NOT NULL,
      decided_at INTEGER
    ) STRICT;
    CREATE UNIQUE INDEX one_official_request ON official_requests(org_id) WHERE status = 'pending';
    CREATE INDEX official_requests_by_org ON official_requests(org_id, id);"""),
    # collabs with an official club (owner, Nov 4; .claude/reports/collab-review.md): an official club's "Don't suggest
    # again" for an initiative; the co-host whose ✓ put an initiative's event in the channel (NULL: the host's own
    # right, kept in step after a lost ✓; set: the post goes when that co-host does); an event's temporary door
    # helpers, any KBTU student a running club's President or Vice picks (scan: tickets only; door: the list too); a team-only
    # event for the club's board (everyone Head+, read from roles at use)
    (126, """CREATE TABLE org_mutes (
      org_id       INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      muted_org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      by_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at   INTEGER NOT NULL,
      PRIMARY KEY (org_id, muted_org_id)
    ) STRICT;
    ALTER TABLE events ADD COLUMN channel_via INTEGER;
    ALTER TABLE events ADD COLUMN for_board INTEGER NOT NULL DEFAULT 0;  -- "For whom": the board (Head+, from roles), not a tag
    CREATE TABLE event_crew (
      event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      kind       TEXT NOT NULL CHECK (kind IN ('scan', 'door')),
      added_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at INTEGER NOT NULL,
      PRIMARY KEY (event_id, user_id)
    ) STRICT;
    CREATE INDEX crew_by_user ON event_crew(user_id);"""),
    # a student ID two people gave (logic/account.id_clash): the one turned away waits in a parked "sid_free" message;
    # whatever frees the ID (the holder fixed a typo, an admin's fix or unlink, a deleted account) sends it now
    (127, """CREATE TRIGGER sid_freed_fix AFTER UPDATE OF student_id ON students WHEN OLD.student_id IS NOT NEW.student_id
    BEGIN
      UPDATE bot_outbox SET send_after = 0 WHERE kind = 'sid_free' AND ref = 'sf:' || OLD.student_id AND sent_at IS NULL;
    END;
    CREATE TRIGGER sid_freed_gone AFTER DELETE ON students
    BEGIN
      UPDATE bot_outbox SET send_after = 0 WHERE kind = 'sid_free' AND ref = 'sf:' || OLD.student_id AND sent_at IS NULL;
    END;"""),
    # The forum feed's public page walks channel messages in order, without sorting all live posts on every poll.
    (128, "CREATE INDEX IF NOT EXISTS fchan_posts_by_message ON fchan_posts(status, tg_msg, id);"),
    # a staff member's muted work items (Admin -> My notifications; logic.seats.STAFF_KINDS): a row is off
    (129, """CREATE TABLE IF NOT EXISTS staff_mutes (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind    TEXT NOT NULL,
        PRIMARY KEY (user_id, kind)
    ) STRICT, WITHOUT ROWID;"""),
    # A club role's title is typed once in any language (src: kk, ru or en; NULL: from before, normalized nightly), the
    # AI fills the other two (ai_wait), never the ones a person corrected (hand: comma-separated languages)
    (130, """ALTER TABLE org_roles ADD COLUMN src TEXT;
    ALTER TABLE org_roles ADD COLUMN hand TEXT NOT NULL DEFAULT '';
    ALTER TABLE org_roles ADD COLUMN ai_wait INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE org_roles ADD COLUMN ai_tries INTEGER NOT NULL DEFAULT 0;"""),
    # always-open recruitment (club presidents, Nov 6): the club's own questions for any-time join requests (JSON, as a
    # round's: kind, text, options, required) and each request's answers (JSON [{q, a}], the question's text kept with it)
    (131, "ALTER TABLE orgs ADD COLUMN join_questions TEXT; ALTER TABLE join_requests ADD COLUMN answers TEXT;"),
    # the Ascent (owner, Nov 6; logic/clubs.py): when a student initiative reached the top, kept once reached (an
    # official club's tools without the ✓)
    (132, "ALTER TABLE orgs ADD COLUMN top_at INTEGER;"),
    # recruitment results in parts (club presidents, Nov 6: "I have to close the round to send results"): each
    # application's own sent_at (told exactly once; a done round's are backfilled), and the round's optional Telegram
    # group invite (https://t.me/... only), shown in the app to the accepted, never by the bot. 133 is left to another branch.
    (133, """ALTER TABLE round_apps ADD COLUMN sent_at INTEGER;
    ALTER TABLE rounds ADD COLUMN group_link TEXT;
    UPDATE round_apps SET sent_at = (SELECT r.sent_at FROM rounds r WHERE r.id = round_apps.round_id)
        WHERE stage != 'withdrawn' AND round_id IN (SELECT id FROM rounds WHERE status = 'done');"""),
    # Admin → Awards → Show QR (owner, Nov 6): a grant link shown as a rotating code on the giver's phone (qr = 1),
    # used only through a fresh signed code (profiles.claim_qr), never by its bare token, and only while the screen
    # keeps renewing its lease (lease_until: a killed or offline screen stops the code within seconds)
    (134, "ALTER TABLE grant_links ADD COLUMN qr INTEGER NOT NULL DEFAULT 0; ALTER TABLE grant_links ADD COLUMN lease_until INTEGER;"),
    # the host club's own people are never its guests (owner, Nov 7): their seats at its upcoming public events go back
    # as seats.joined does (seats.TEAM_SEATS: a free event's, a waitlist place; a paid seat or hold stays), their 2-hour
    # reminders with them; seats.refill moves the waitlists in at the start that follows
    (135, """UPDATE registrations SET status = 'cancelled', cancel_reason = 'removed', hold_until = NULL, waitlisted_at = NULL,
        updated_at = CAST(strftime('%s', 'now') AS INTEGER)
      WHERE checked_in_at IS NULL AND (status = 'waitlist' OR status IN ('going', 'hold')
          AND event_id IN (SELECT id FROM events WHERE price IS NULL))
        AND EXISTS (SELECT 1 FROM events e JOIN org_members m ON m.org_id = e.org_id AND m.user_id = registrations.user_id
          WHERE e.id = registrations.event_id AND e.status = 'published' AND e.visibility = 'public'
            AND e.starts_at > CAST(strftime('%s', 'now') AS INTEGER));
    DELETE FROM bot_outbox WHERE kind = 'remind_2h' AND sent_at IS NULL AND EXISTS (SELECT 1 FROM registrations r
      WHERE r.user_id = bot_outbox.user_id AND r.cancel_reason = 'removed' AND bot_outbox.ref LIKE 'event:' || r.event_id || ':%');"""),
    # (Nov 7) the 3rd years' answer under the incubator's elective post (admin announce3): more like it? NULL: never asked
    (136, "ALTER TABLE users ADD COLUMN announce_ok INTEGER;"),
    # the door opened early by the club's President or a Vice (organizing.open_door); NULL: at T-30 by itself (core.door_at)
    # deploy: a door the old 3-hour rule already let people through stays open (from T-3h, as it was)
    (137, """ALTER TABLE events ADD COLUMN door_open_at INTEGER;
    UPDATE events SET door_open_at = starts_at - 10800 WHERE status = 'published' AND starts_at - 10800 <= CAST(strftime('%s', 'now') AS INTEGER)
      AND CAST(strftime('%s', 'now') AS INTEGER) < starts_at - 1800 AND EXISTS (SELECT 1 FROM registrations r WHERE r.event_id = events.id AND r.checked_in_at IS NOT NULL);"""),
    # a host club's member asks its President or a Vice to come to its public event as a guest (owner, Nov 7; seats.team_ask):
    # one row per person per event; 'yes' lets them sign up and keeps their seat from seats.joined
    (138, """CREATE TABLE team_asks (
      event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','yes','no')),
      created_at INTEGER NOT NULL,
      decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      decided_at INTEGER,
      PRIMARY KEY (event_id, user_id)
    ) STRICT;"""),
    # guests' photos always on (owner, Nov 8): "Photos from participants" is gone; the column stays, unread
    (139, "UPDATE events SET album_open = 1 WHERE album_open = 0;"),
    # ticket codes are 4 characters, unique within their event (owner, Nov 8; seats._ticket_code): stored as
    # '<event id>-<code>', so the column's own UNIQUE (not droppable without a rebuild) keeps them apart per event.
    # Every ticket gets a new one, the old 6-character codes stop working (owner). OR IGNORE skips a row whose draw
    # collides in its event; it draws again on the next pass; a row still unset after 8 passes (~never) fails the CHECK
    # below and with it the whole step
    (140, "UPDATE registrations SET ticket_code = 'old:' || id;\n" + "\n".join([
        """UPDATE OR IGNORE registrations SET ticket_code = event_id || '-' || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1)
          || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1) || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1)
          || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1) WHERE ticket_code GLOB 'old:*';"""] * 8)
     + "\nUPDATE registrations SET status = 'unset' WHERE ticket_code GLOB 'old:*';"),
    # Sunday classes are the portal's online duplicates of the week's (owner, Nov 8): the import drops them, the old ones go
    (141, "DELETE FROM schedule_classes WHERE weekday = 7;"),
    # an offline casting is a marked post (newsfeed.casting_state): come at this time to this place, no sign-up
    (142, """ALTER TABLE posts ADD COLUMN casting_from INTEGER;
    ALTER TABLE posts ADD COLUMN casting_to INTEGER;
    ALTER TABLE posts ADD COLUMN casting_place TEXT;
    ALTER TABLE posts ADD COLUMN casting_cancelled_at INTEGER;
    CREATE INDEX posts_casting ON posts(casting_to) WHERE casting_to IS NOT NULL;"""),
    # a club's interest (the Clubs tab's tiles): it/art/sport/business/science/volunteer, NULL none; checked in clubs.update_org
    (143, "ALTER TABLE orgs ADD COLUMN category TEXT;"),
    # a check-in QR is good only while something shows it: each poll of a /show screen or an organizer's phone renews this
    # (checkin.mark). NULL: never shown since this column came, so a session running through the deploy isn't cut off
    (144, "ALTER TABLE qr_sessions ADD COLUMN lease_until INTEGER;"),
    # who an organizer let help run a check-in, by a QR (checkin.hand); help_until: that QR's lease, as lease_until above
    (145, """ALTER TABLE qr_sessions ADD COLUMN help_until INTEGER;
    ALTER TABLE qr_sessions ADD COLUMN help_gen INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE qr_helpers (
      session_id INTEGER NOT NULL REFERENCES qr_sessions(id),
      user_id INTEGER NOT NULL REFERENCES users(id),
      added_by INTEGER REFERENCES users(id),
      created_at INTEGER NOT NULL,
      PRIMARY KEY (session_id, user_id));"""),
    # Stars given on "Support the app" (logic/stars.py): the charge, its size, its time, and nothing about who gave
    (146, """CREATE TABLE star_gifts (
      charge_id TEXT PRIMARY KEY,
      amount INTEGER NOT NULL CHECK (amount > 0),
      created_at INTEGER NOT NULL) WITHOUT ROWID;"""),
    # anonymous usage counters (logic/stats.py): daily totals only, no person in them
    (147, """CREATE TABLE usage_days (
      day INTEGER NOT NULL,
      key TEXT NOT NULL,
      n INTEGER NOT NULL,
      PRIMARY KEY (day, key)) WITHOUT ROWID;"""),
    # the volunteers ledger of one club (logic/vol.py, VOLUNTEERS=<slug>): a record per volunteer apart from any account
    # (imported people without one too), its shifts from check-in or by hand, misses, the President's edits, who may read it
    (148, """CREATE TABLE vol_batches (
      id INTEGER PRIMARY KEY,
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      source TEXT NOT NULL,
      sha TEXT NOT NULL,
      counts TEXT NOT NULL DEFAULT '{}',
      created_at INTEGER NOT NULL,
      undone_at INTEGER) STRICT;
    CREATE TABLE vol_people (
      id INTEGER PRIMARY KEY,
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      user_id INTEGER REFERENCES users(id),
      name TEXT NOT NULL DEFAULT '',
      tg TEXT,
      raw TEXT NOT NULL DEFAULT '{}',
      balance INTEGER NOT NULL DEFAULT 0,
      batch_id INTEGER REFERENCES vol_batches(id) ON DELETE SET NULL,
      created_at INTEGER NOT NULL) STRICT;
    CREATE UNIQUE INDEX vol_people_user ON vol_people(org_id, user_id) WHERE user_id IS NOT NULL;
    CREATE TABLE vol_keys (
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      ikey TEXT NOT NULL,
      vol_id INTEGER NOT NULL REFERENCES vol_people(id) ON DELETE CASCADE,
      PRIMARY KEY (org_id, ikey)) STRICT;
    CREATE INDEX vol_keys_by_vol ON vol_keys(vol_id);
    CREATE TABLE vol_ties (
      vol_id INTEGER NOT NULL REFERENCES vol_people(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id),
      PRIMARY KEY (vol_id, user_id)) STRICT, WITHOUT ROWID;
    CREATE INDEX vol_ties_by_user ON vol_ties(user_id);
    CREATE TABLE vol_gone (
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      khash TEXT NOT NULL,
      PRIMARY KEY (org_id, khash)) STRICT, WITHOUT ROWID;
    CREATE TABLE vol_meets (
      session_id INTEGER PRIMARY KEY REFERENCES qr_sessions(id) ON DELETE CASCADE,
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      team INTEGER NOT NULL DEFAULT 0,
      expected_n INTEGER NOT NULL DEFAULT 0,
      held INTEGER,
      created_at INTEGER NOT NULL) STRICT;
    CREATE TABLE vol_expected (
      session_id INTEGER NOT NULL REFERENCES vol_meets(session_id) ON DELETE CASCADE,
      vol_id INTEGER NOT NULL REFERENCES vol_people(id) ON DELETE CASCADE,
      PRIMARY KEY (session_id, vol_id)) STRICT, WITHOUT ROWID;
    CREATE TABLE vol_shifts (
      id INTEGER PRIMARY KEY,
      vol_id INTEGER NOT NULL REFERENCES vol_people(id) ON DELETE CASCADE,
      session_id INTEGER REFERENCES qr_sessions(id) ON DELETE SET NULL,
      in_at INTEGER NOT NULL,
      out_at INTEGER,
      in_by INTEGER REFERENCES users(id),
      out_by INTEGER REFERENCES users(id),
      gone_at INTEGER) STRICT;
    CREATE INDEX vol_shifts_by_vol ON vol_shifts(vol_id);
    CREATE INDEX vol_shifts_by_session ON vol_shifts(session_id);
    CREATE TABLE vol_misses (
      id INTEGER PRIMARY KEY,
      vol_id INTEGER NOT NULL REFERENCES vol_people(id) ON DELETE CASCADE,
      session_id INTEGER REFERENCES qr_sessions(id) ON DELETE SET NULL,
      n INTEGER NOT NULL CHECK (n IN (1, -1)),
      by INTEGER REFERENCES users(id),
      at INTEGER NOT NULL,
      gone_at INTEGER) STRICT;
    CREATE INDEX vol_misses_by_vol ON vol_misses(vol_id);
    CREATE TABLE vol_edits (
      id INTEGER PRIMARY KEY,
      vol_id INTEGER NOT NULL REFERENCES vol_people(id) ON DELETE CASCADE,
      what TEXT NOT NULL,
      ref INTEGER,
      old TEXT,
      new TEXT,
      reason TEXT NOT NULL DEFAULT '',
      by INTEGER REFERENCES users(id),
      at INTEGER NOT NULL) STRICT;
    CREATE INDEX vol_edits_by_vol ON vol_edits(vol_id);
    CREATE TABLE vol_access (
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id),
      granted_by INTEGER REFERENCES users(id),
      at INTEGER NOT NULL,
      PRIMARY KEY (org_id, user_id)) STRICT;
    CREATE TRIGGER vol_access_gone AFTER DELETE ON org_members BEGIN
      DELETE FROM vol_access WHERE org_id = OLD.org_id AND user_id = OLD.user_id;
    END;"""),
    # appeals to the Student Government (logic/appeals.py, APPEALS): the appeal without its author, the author link apart
    # (never shown to SG for an anonymous one), the day's sends for the quota, the section's consent, SG's people
    (149, """CREATE TABLE appeals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,  -- never reused: SG's answer to a deleted one can't land on the next one
      topic TEXT,
      body TEXT NOT NULL,
      anon INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'work', 'closed')),
      answer TEXT,
      created_at INTEGER NOT NULL,
      due_at INTEGER NOT NULL,
      answered_at INTEGER,
      closed_at INTEGER,
      nonce TEXT) STRICT;
    CREATE TABLE appeal_authors (
      appeal_id INTEGER PRIMARY KEY REFERENCES appeals(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id)) STRICT;
    CREATE INDEX appeal_authors_user ON appeal_authors(user_id);
    CREATE TABLE appeal_sends (
      user_id INTEGER NOT NULL REFERENCES users(id),
      at INTEGER NOT NULL) STRICT;
    CREATE INDEX appeal_sends_user ON appeal_sends(user_id, at);
    CREATE TABLE appeal_consents (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      version TEXT NOT NULL,
      at INTEGER NOT NULL) STRICT;
    CREATE TABLE appeal_staff (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      at INTEGER NOT NULL) STRICT;"""),
    # (Nov 11) the Gallery (logic/gallery.py): a photo a student posted under their name, of KBTU or of an event they went
    # to (that one is in its album too, event_photos).
    # And a photo's two report reasons ("breaks the rules", "I'm in it and against it"): the CHECK takes them, rebuilt as 114.
    # renumbered at ship: other branches take 150-152 too
    (150, """CREATE TABLE gallery_photos (
      file_id    INTEGER PRIMARY KEY REFERENCES files(id),
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      event_id   INTEGER REFERENCES events(id) ON DELETE SET NULL,  -- its event gone: still the student's, a plain KBTU photo
      created_at INTEGER NOT NULL) STRICT;
    CREATE INDEX gallery_by_user ON gallery_photos(user_id, created_at);
    CREATE TABLE reports6 (
        id INTEGER PRIMARY KEY,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        target TEXT NOT NULL CHECK (target IN ('post', 'comment', 'event', 'user', 'org', 'photo', 'ask', 'thread', 'reply', 'fpost')),
        target_id INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK (reason IN ('spam', 'insult', 'danger', 'other', 'rules', 'me')),
        note TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
        created_at INTEGER NOT NULL,
        resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        resolved_at INTEGER
    ) STRICT;
    INSERT INTO reports6 SELECT id, reporter_id, target, target_id, reason, note, status, created_at, resolved_by, resolved_at FROM reports;
    DROP TABLE reports;
    ALTER TABLE reports6 RENAME TO reports;
    CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id) WHERE status = 'open';"""),
    # a club's members mirrored from its Telegram chats (logic/chatsync.py, CHAT_SYNC): the main chat is the membership,
    # a department's chat that department. Linked by the app's creator alone (admin chatsync). A sweep's findings wait in
    # chat_sync_todo until it ends (an implausible drop pauses instead of removing); last_update/last_date: the newest
    # chat_member update applied (a replay after a restart is skipped; a sweep's reply older than it is dropped);
    # chat_sync_ask: someone just verified or agreed, to look up in the linked chats once. member_tags.sync: a department the
    # sync gave, which never makes its Head a manager of it (only a department given by hand does)
    (151, """CREATE TABLE chat_sync (
      chat_id INTEGER PRIMARY KEY,
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      kind TEXT NOT NULL CHECK (kind IN ('main', 'dept')),
      tag_id INTEGER REFERENCES org_tags(id) ON DELETE CASCADE,
      paused TEXT,
      sweep TEXT CHECK (sweep IN ('dry', 'apply', 'night')),
      sweep_pos INTEGER NOT NULL DEFAULT 0,
      result TEXT,
      last_update INTEGER NOT NULL DEFAULT 0,
      last_date INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL,
      CHECK ((kind = 'dept') = (tag_id IS NOT NULL))) STRICT;
    CREATE UNIQUE INDEX chat_sync_main ON chat_sync(org_id) WHERE kind = 'main';
    CREATE TABLE chat_sync_todo (
      chat_id INTEGER NOT NULL REFERENCES chat_sync(chat_id) ON DELETE CASCADE ON UPDATE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id),
      op TEXT NOT NULL CHECK (op IN ('add', 'drop')),
      PRIMARY KEY (chat_id, user_id)) STRICT, WITHOUT ROWID;
    CREATE INDEX chat_sync_todo_user ON chat_sync_todo(user_id);
    CREATE TABLE chat_sync_ask (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      at INTEGER NOT NULL) STRICT;
    ALTER TABLE member_tags ADD COLUMN sync INTEGER NOT NULL DEFAULT 0;"""),
    # photos on forum channel posts (fchannel.add_photo, owner Nov 5): a re-encoded upload (no EXIF) under a random name;
    # user_id: the uploader while it is on no post (then NULL: the post says whose). A row leaving by any way (the
    # author's delete, the sweep, a cascade) queues its files for the disk (fchpic:<path>, the bot's round drops them).
    # tg_unpost.photo: a photo message, edited to a blank picture when Telegram won't delete it
    (152, """CREATE TABLE fchan_photos (
      id         INTEGER PRIMARY KEY,
      user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
      post_id    INTEGER REFERENCES fchan_posts(id) ON DELETE CASCADE,
      n          INTEGER NOT NULL DEFAULT 0,
      path       TEXT NOT NULL,
      width      INTEGER NOT NULL,
      height     INTEGER NOT NULL,
      color      TEXT,
      msg        INTEGER,
      created_at INTEGER NOT NULL) STRICT;
    CREATE INDEX fchan_photos_by_post ON fchan_photos(post_id, n);
    CREATE INDEX fchan_photos_by_user ON fchan_photos(user_id);
    CREATE INDEX fchan_photos_by_msg ON fchan_photos(msg) WHERE msg > 0;
    CREATE TRIGGER fchan_photo_gone AFTER DELETE ON fchan_photos BEGIN
      INSERT OR IGNORE INTO meta (key, value) VALUES ('fchpic:' || OLD.path, '1');
    END;
    ALTER TABLE tg_unpost ADD COLUMN photo INTEGER NOT NULL DEFAULT 0;"""),
    # the forum UI rework (Nov 10): posted_at, when the channel got the post (the time the app shows everyone: the
    # writing time told when a held anonymous post was written); the AI's tip and the words it stopped at, kept with its
    # reason so the author's held post still says them after a reload
    (153, """ALTER TABLE fchan_posts ADD COLUMN posted_at INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN ai_fix TEXT;
    ALTER TABLE fchan_posts ADD COLUMN ai_quote TEXT;"""),
    # the old one-time fr_ friend links: none issued since Nov 2 (one link, r_), the last died on Nov 9
    (154, "DROP TABLE IF EXISTS friend_links;"),
    # a request its sender took back after a quiet decline: out of the sender's list, the 30 days still held (profiles.take_back_request)
    (155, "ALTER TABLE friend_requests ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;"),
    # the volunteers ledger's door handed over by a one-time link (logic/vol.py hand, take): only the token's hash;
    # user_id: the first eligible account that opened it. One live link a session. vol_resolve_from: when answering for
    # the unmarked began; a session finished before it keeps its open shifts at 0
    (156, """CREATE TABLE vol_hands (
      id INTEGER PRIMARY KEY,
      session_id INTEGER NOT NULL REFERENCES qr_sessions(id) ON DELETE CASCADE,
      token TEXT NOT NULL UNIQUE,
      made_by INTEGER REFERENCES users(id),
      user_id INTEGER REFERENCES users(id),
      created_at INTEGER NOT NULL,
      taken_at INTEGER,
      revoked_at INTEGER) STRICT;
    CREATE UNIQUE INDEX vol_hands_live ON vol_hands(session_id) WHERE revoked_at IS NULL;
    CREATE INDEX vol_hands_by_user ON vol_hands(user_id);
    INSERT OR IGNORE INTO meta (key, value) VALUES ('vol_resolve_from', CAST(strftime('%s', 'now') AS TEXT));"""),
    # (Nov 11) one shared gallery: a photo of no event says what it is about (logic/gallery.py TOPICS). A photo of no
    # event already lives in gallery_photos (event_id NULL), so a nullable column is all it takes: no new table, no
    # rebuild. NULL: an event's photo, or one posted before topics (read as "other").
    # 157: 155 is the friends branch's, 156 the volunteers' (it lands first; until then the numbers have a gap).
    (157, "ALTER TABLE gallery_photos ADD COLUMN topic TEXT CHECK (topic IN ('campus', 'study', 'life', 'other'));"),
    # (Nov 11) a club's report after its event (logic/evreports.py, REPORTS=1): which department ran it (a tag marked
    # department, the club's own), the guests counted by hand, a note; who filled it first and who edited it last.
    # report_marks: a team member's attendance at it, one status each. A Vice's role with its own toggles gets the new
    # "reports" right, as a Vice without them has it (core.OWN_FROM); again on a replay, it isn't added twice.
    (158, """CREATE TABLE event_reports (
      event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
      dept_id INTEGER REFERENCES org_tags(id) ON DELETE SET NULL,
      guests INTEGER CHECK (guests BETWEEN 0 AND 100000),
      note TEXT NOT NULL DEFAULT '',
      filled_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      filled_at INTEGER NOT NULL,
      edited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      edited_at INTEGER NOT NULL) STRICT;
    CREATE TABLE report_marks (
      event_id INTEGER NOT NULL REFERENCES event_reports(event_id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status TEXT NOT NULL CHECK (status IN ('present', 'late', 'absent', 'excused')),
      PRIMARY KEY (event_id, user_id)) STRICT;
    CREATE INDEX report_marks_by_user ON report_marks(user_id);
    UPDATE org_roles SET rights = rights || ',reports' WHERE level = 'vice' AND rights IS NOT NULL AND ',' || rights || ',' NOT LIKE '%,reports,%';"""),
    # (Nov 12) event reports' own consent (evreports.CONSENT, as appeal_consents): one per person, for every club; no
    # row, no report of mine and no mark of me
    (159, """CREATE TABLE report_consents (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      version TEXT NOT NULL,
      at INTEGER NOT NULL) STRICT;"""),
    # (Nov 12) a report per club: the host and its accepted co-host each write their own (evreports.py). 158's tables
    # are keyed by the event alone and SQLite can't change a primary key, so new ones keyed by (event, club); 158's rows
    # move over as the host's reports, then its two tables go (nothing else references them; the marks, their only
    # child, are dropped first, so nothing cascades).
    (160, """CREATE TABLE club_reports (
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      dept_id INTEGER REFERENCES org_tags(id) ON DELETE SET NULL,
      guests INTEGER CHECK (guests BETWEEN 0 AND 100000),
      note TEXT NOT NULL DEFAULT '',
      filled_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      filled_at INTEGER NOT NULL,
      edited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      edited_at INTEGER NOT NULL,
      PRIMARY KEY (event_id, org_id)) STRICT;
    CREATE TABLE club_report_marks (
      event_id INTEGER NOT NULL,
      org_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status TEXT NOT NULL CHECK (status IN ('present', 'late', 'absent', 'excused')),
      PRIMARY KEY (event_id, org_id, user_id),
      FOREIGN KEY (event_id, org_id) REFERENCES club_reports(event_id, org_id) ON DELETE CASCADE) STRICT;
    CREATE INDEX club_report_marks_by_user ON club_report_marks(user_id);
    INSERT INTO club_reports (event_id, org_id, dept_id, guests, note, filled_by, filled_at, edited_by, edited_at)
      SELECT r.event_id, e.org_id, r.dept_id, r.guests, r.note, r.filled_by, r.filled_at, r.edited_by, r.edited_at
      FROM event_reports r JOIN events e ON e.id = r.event_id;
    INSERT INTO club_report_marks (event_id, org_id, user_id, status)
      SELECT k.event_id, e.org_id, k.user_id, k.status FROM report_marks k JOIN events e ON e.id = k.event_id;
    DROP TABLE report_marks;
    DROP TABLE event_reports;"""),
    # (Nov 12) team events (logic/evteams.py): a free event's teams of team_min..team_max people (NULL: not a team
    # event). A team is its name (unique in the event by name_key: NFKC, casefolded), its invite token and the "find us
    # teammates" switch; its roster is its members in the order they came (the row id), the first one its captain, so a captain who leaves hands over by itself. A member
    # is a 'going' registration: any way out of the event (cancelled, deleted with the account) takes them out of the
    # team, and an empty team goes, by the triggers below, whatever code path it was. team_consents: the feature's own
    # consent (evteams.CONSENT, as report_consents): no row, never in a team.
    (161, """ALTER TABLE events ADD COLUMN team_min INTEGER;
    ALTER TABLE events ADD COLUMN team_max INTEGER;
    CREATE TABLE event_teams (
      id INTEGER PRIMARY KEY,
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      name_key TEXT NOT NULL,
      token TEXT NOT NULL UNIQUE,
      open INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL,
      UNIQUE (event_id, name_key)) STRICT;
    CREATE TABLE event_team_members (
      id INTEGER PRIMARY KEY,
      team_id INTEGER NOT NULL REFERENCES event_teams(id) ON DELETE CASCADE,
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id),
      UNIQUE (event_id, user_id)) STRICT;
    CREATE INDEX event_team_members_by_team ON event_team_members(team_id);
    CREATE INDEX event_team_members_by_user ON event_team_members(user_id);
    CREATE TRIGGER event_team_reg_out AFTER UPDATE OF status ON registrations WHEN NEW.status != 'going' BEGIN
      DELETE FROM event_team_members WHERE event_id = NEW.event_id AND user_id = NEW.user_id;
    END;
    CREATE TRIGGER event_team_reg_gone AFTER DELETE ON registrations BEGIN
      DELETE FROM event_team_members WHERE event_id = OLD.event_id AND user_id = OLD.user_id;
    END;
    CREATE TRIGGER event_team_empty AFTER DELETE ON event_team_members BEGIN
      DELETE FROM event_teams WHERE id = OLD.team_id AND NOT EXISTS (SELECT 1 FROM event_team_members WHERE team_id = OLD.team_id);
    END;
    CREATE TABLE team_consents (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      version TEXT NOT NULL,
      at INTEGER NOT NULL) STRICT;"""),
    # (Nov 13) an album in the order its photos were taken: the time from the upload's EXIF (media.taken; the one fact
    # kept of it), unix seconds with the camera's sub-seconds; NULL (no EXIF, or uploaded before): its upload time
    (162, "ALTER TABLE files ADD COLUMN taken_at REAL;"),
    # a check-in marked by hand from the student's badge QR (checkin.badge): who marked it
    (163, "ALTER TABLE qr_marks ADD COLUMN marked_by INTEGER REFERENCES users(id) ON DELETE SET NULL;"),
    # (Nov 13) a club's group moderated for swearing (logic/chatmod.py): chats.swear is its switch, off by default. A hit
    # is a row: the chat, the person's Telegram id (and app id when known), the matched stem of our own list (never the
    # message), when, its warning number (1..3), whether it muted. Nothing for clean messages; 90 days (daily).
    # chats.swear_miss: the bot's rights it lacks there ("delete", "ban", comma-joined; NULL: none), the filter paused.
    (164, """ALTER TABLE chats ADD COLUMN swear INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE chats ADD COLUMN swear_miss TEXT;
    CREATE TABLE swear_hits (
      id INTEGER PRIMARY KEY,
      chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
      tg_id INTEGER NOT NULL,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      stem TEXT NOT NULL,
      at INTEGER NOT NULL,
      warn INTEGER NOT NULL,
      muted INTEGER NOT NULL DEFAULT 0) STRICT;
    CREATE INDEX swear_hits_by_person ON swear_hits(chat_id, tg_id, at);
    CREATE INDEX swear_hits_by_user ON swear_hits(user_id);
    CREATE INDEX chats_by_tg ON chats(tg_chat_id);"""),
    # (Nov 13) /all calls who the bot saw in a club's chat too (Telegram gives bots no member list): Telegram ids
    # alone, no names or words, with the club that held the chat then; forgotten on leaving, with the chat, as soon
    # as another club or none holds it (triggers: every way a link changes), and 180 days after they were last seen
    (165, _CHAT_SEEN),
    # (Nov 13) a club's team marked at one of its events (checkin.crew): a club session tied to the event, apart from
    # its guests' session (event_id); one per event; the event deleted, the attendance stays
    (166, """ALTER TABLE qr_sessions ADD COLUMN crew_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL;
    CREATE UNIQUE INDEX qr_sessions_by_crew ON qr_sessions(crew_event_id) WHERE crew_event_id IS NOT NULL;"""),
    # (Nov 13) "Solved by your appeals" (appeals.solved): SG's public lines, what students raised and what changed. No
    # link to any appeal by design; who wrote it for the audit only (never sent), emptied when that account goes.
    # gone_at: deleted, still undoable for a day (appeals.forget)
    (167, """CREATE TABLE appeal_solved (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      raised TEXT NOT NULL,
      changed TEXT NOT NULL,
      topic TEXT,
      created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at INTEGER NOT NULL,
      gone_at INTEGER) STRICT;"""),
    # (Nov 13) a school's own event only for its students (seats._visible): the school's slug, NULL for everyone
    (168, "ALTER TABLE events ADD COLUMN school TEXT;"),
    # (Nov 14) a chat our bot was made admin in, no club holding it, remembered for the one who did it (Telegram's
    # action performer) for ten minutes: Studio → Chats lists it to him to link (logic/chatlist.py bot_admin, claim_wait)
    (169, """CREATE TABLE chat_waits (
      id INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id),
      chat_id INTEGER NOT NULL,
      chat TEXT NOT NULL,
      invite TEXT,
      until INTEGER NOT NULL,
      UNIQUE (user_id, chat_id)) STRICT;
    CREATE INDEX chat_waits_by_chat ON chat_waits(chat_id);"""),
    # /all in a chat no club holds (owner, Nov 14): whom the bot saw there, Telegram ids only (chat_seen without a club)
    (170, """CREATE TABLE chat_seen_free (
      chat_id INTEGER NOT NULL,
      tg_id INTEGER NOT NULL,
      seen_at INTEGER NOT NULL,
      PRIMARY KEY (chat_id, tg_id)) STRICT, WITHOUT ROWID;"""),
    # (Nov 14, the Mark screen) whom an event's door records: guests, its team, or both (NULL: both, the team routed by
    # membership, as before; checkin._team). The Talent Show (34) marked its team only (it was TEAM_DOOR in the code).
    # qr_hand_marks: a team list's row with no account marked by hand (who: 'r<roster_pending id>' or 'x<qr_expected email>');
    # a member's hand mark is a qr_marks row with marked_by
    (171, """ALTER TABLE events ADD COLUMN door_audience TEXT CHECK (door_audience IN ('guests', 'team', 'both'));
    UPDATE events SET door_audience = 'team' WHERE id = 34;
    CREATE TABLE qr_hand_marks (
      session_id INTEGER NOT NULL REFERENCES qr_sessions(id) ON DELETE CASCADE,
      who        TEXT NOT NULL,
      marked_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
      at         INTEGER NOT NULL,
      PRIMARY KEY (session_id, who)) STRICT;"""),
]


BUSY_MS = 15000  # a write's wait for the lock (maybe() waits less)


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(f"PRAGMA busy_timeout = {BUSY_MS}")  # a write waits its turn: 600 sign-ups at once took 11 s on a laptop core
    con.execute("PRAGMA secure_delete = ON")  # deleted rows' text doesn't linger in free pages (H2)
    con.execute("PRAGMA synchronous = NORMAL")  # with WAL: no corruption on a crash, fsync only at checkpoints
    # reads straight from the OS page cache, shared by every worker and pooled connection, instead of each copying
    # pages into its own small cache (writes still go through the WAL)
    con.execute("PRAGMA mmap_size = 268435456")
    return con


class Pool:
    """Open connections kept for the next request. A new connection reads the whole schema before its first query
    (~4 ms on a laptop core, more than most requests take; load test); a kept one starts at once. A request
    has its connection to itself until it gives it back."""

    def __init__(self, path: str) -> None:
        self.path, self.idle = path, queue.SimpleQueue()

    @contextlib.contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        try:
            con = self.idle.get_nowait()
        except queue.Empty:
            con = connect(self.path)
        try:
            yield con
        finally:
            if con.in_transaction:  # a request that died mid-write leaves nothing open for the next one
                con.execute("ROLLBACK")
            self.idle.put(con)


def init(path: str, after: Callable[[sqlite3.Connection], None] | None = None) -> None:
    """Creates the database or brings it up to date. Each step is one transaction (DDL is transactional in
    SQLite), so a failure leaves the file as it was. Worker processes start together: one migrates while the
    rest wait on the lock file, then find nothing left to do. `after` runs under the same lock (the data's own
    catch-up, e.g. achievement levels)."""
    with open(f"{path}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _init(path)
        if after:
            con = connect(path)
            try:
                after(con)
            finally:
                con.close()


def _init(path: str) -> None:
    con = connect(path)
    try:
        con.execute("PRAGMA journal_mode = WAL")
        version = con.execute("PRAGMA user_version").fetchone()[0]
        steps = ([(1, SCHEMA)] if version == 0 else []) + [m for m in MIGRATIONS if m[0] > version]
        if version and steps:  # a live file about to change: a full copy next to it first (the way back, by hand)
            con.execute("VACUUM INTO ?", (f"{path}.v{version}-{int(time.time())}.bak",))
        for target, sql in steps:
            try:
                con.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {target};\nCOMMIT;")
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
    finally:
        con.close()


@contextlib.contextmanager
def tx(con: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """A write transaction that holds the write lock from the start; inside another one it joins it (the outer one
    commits or rolls back for both)."""
    if con.in_transaction:
        yield con
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def maybe(con: sqlite3.Connection, fn: Callable, *args, ms: int = 200):
    """A best-effort write on a read (seen_at, a roster match on /api/me): fn(*args) in one transaction that waits for
    the write lock `ms` at most and is skipped (rolled back, None) while a burst holds it; the next call tries again.
    A GET never waits connect()'s 15 s behind someone else's writes."""
    con.execute(f"PRAGMA busy_timeout = {int(ms)}")
    try:
        with tx(con):
            return fn(*args)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc) and "busy" not in str(exc):
            raise
        return None
    finally:
        con.execute(f"PRAGMA busy_timeout = {BUSY_MS}")
