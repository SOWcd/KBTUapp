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
MIGRATIONS: list[tuple[int, str]] = [
    (2, "ALTER TABLE files ADD COLUMN color TEXT;"),   # a photo's average colour: the event sheet's tint (Oct 4)
    # a club's socials (Instagram, TikTok, YouTube, Telegram, a site), shown on its sheet; the old single link moves in
    (3, "ALTER TABLE orgs ADD COLUMN links TEXT NOT NULL DEFAULT '[]'; UPDATE orgs SET links = json_array(link) WHERE link IS NOT NULL;"),
    # join applications (§4.5): open unless the club closes them in Studio; the "recruiting until" date goes (owner, Oct 4)
    (4, "ALTER TABLE orgs ADD COLUMN recruiting INTEGER NOT NULL DEFAULT 1; UPDATE orgs SET recruiting = 0 WHERE kind IN ('school','office','app');"
        " ALTER TABLE orgs DROP COLUMN recruiting_until;"),
    # the badge QR (§4.4, owner Oct 4): a random code per student, so nobody can make a QR from a user id;
    # walk_in marks a registration made at the door with that QR
    (5, "ALTER TABLE users ADD COLUMN qr_code TEXT; CREATE UNIQUE INDEX users_qr ON users(qr_code);"
        " ALTER TABLE registrations ADD COLUMN walk_in INTEGER NOT NULL DEFAULT 0;"),
    # the point of the cover every frame keeps in view, "x,y" from 0 to 1 (Oct 4: one photo fills a tall Feed slide,
    # the wide sheet and a square thumbnail, so the organizer marks what matters instead of one crop)
    (6, "ALTER TABLE events ADD COLUMN cover_focus TEXT;"),
    # checked in by name at the door (no QR: a dead phone), shown "by hand" to the organizer and in the CSV (Oct 4)
    (7, "ALTER TABLE registrations ADD COLUMN checkin_manual INTEGER NOT NULL DEFAULT 0;"),
    # an organizer's update on an event, pinned under its title; the bot only says there is one (Oct 4)
    (8, """CREATE TABLE event_updates (
        id INTEGER PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        body TEXT NOT NULL CHECK (length(body) BETWEEN 2 AND 300),
        created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX event_updates_by_event ON event_updates(event_id, created_at);"""),
    # one-tap rating after an event: only people checked in, anonymous to the club (Oct 4)
    (9, """CREATE TABLE event_ratings (
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
        comment TEXT NOT NULL DEFAULT '' CHECK (length(comment) <= 300),
        created_at INTEGER NOT NULL,
        PRIMARY KEY (event_id, user_id)
    ) STRICT;"""),
    # the personal calendar feed: everything I go to, subscribed once in the phone's calendar (Oct 5)
    (10, """ALTER TABLE users ADD COLUMN cal_token TEXT;
    CREATE UNIQUE INDEX users_cal_token ON users(cal_token);"""),
    # the unlock moment: the level the app has already celebrated (the bot's message goes once by its own ref)
    (11, "ALTER TABLE achievement_levels ADD COLUMN seen INTEGER NOT NULL DEFAULT 0;"),
    # a student's number on the card: the order of first KBTU sign-in, kept for good; the Creator's card shows 00000 and
    # takes none, so "First 500" is the cards 00001-00500 (owner, Oct 5). Students so far: by when they signed in.
    (12, """ALTER TABLE users ADD COLUMN card_no INTEGER;
    CREATE UNIQUE INDEX users_card_no ON users(card_no);
    UPDATE users SET card_no = (SELECT n FROM (SELECT s.user_id, ROW_NUMBER() OVER (ORDER BY s.verified_at, s.user_id) AS n
            FROM students s JOIN users x ON x.id = s.user_id WHERE x.is_founder = 0) r WHERE r.user_id = users.id)
        WHERE is_founder = 0 AND id IN (SELECT user_id FROM students);"""),
    # a registration deadline (NULL = until the start), and a paid event's free seats for 1st-year students: "the first
    # 100 tickets free for the 1st course" (owner, Oct 5); `free` marks a registration holding one of them
    (13, """ALTER TABLE events ADD COLUMN reg_until INTEGER;
    ALTER TABLE events ADD COLUMN free_first INTEGER CHECK (free_first > 0);
    ALTER TABLE registrations ADD COLUMN free INTEGER NOT NULL DEFAULT 0;"""),
    # Team 2.0 (owner, Oct 5; SPEC §2b): a club's own roles (a name and colour on one of the levels), tags (groups of
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
    # Studio's "questions waiting" go once the reader has read them (owner, Oct 5: "they stay after I read and answer"):
    # the newest comment under an event when each of the club's Head+ last opened them (ids, not seconds: exact)
    (15, """CREATE TABLE comment_reads (
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        last_id INTEGER NOT NULL,
        PRIMARY KEY (event_id, user_id)
    ) STRICT;"""),
    # a nickname and my own photo (owner, Oct 5; SPEC §3): everyone sees the nick, organizers the real name beside it;
    # avatar_tg is the "Photo from Telegram" switch, off once I upload my own (it goes in users.avatar_file_id)
    (16, """ALTER TABLE users ADD COLUMN nick TEXT CHECK (nick IS NULL OR length(nick) BETWEEN 2 AND 24);
    ALTER TABLE users ADD COLUMN avatar_tg INTEGER NOT NULL DEFAULT 1;"""),
    # wrong KBTU passwords per account (§4.1: 5 in 15 min) in the database, so every worker process counts the same ones;
    # two partial indexes the load test asked for (Oct 7): expired holds (swept before every Afisha) and "Life of the
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
    # Studio part 2 "Meetings" (owner's go, Oct 5; SPEC §2b): a team-only event the whole club (or one tag) is expected at;
    # "Can't make it" says why (registrations.note); a missed meeting's strike names it, one per meeting per person
    (19, """ALTER TABLE events ADD COLUMN meeting INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE events ADD COLUMN meeting_tag INTEGER REFERENCES org_tags(id) ON DELETE SET NULL;
    ALTER TABLE registrations ADD COLUMN note TEXT CHECK (note IS NULL OR length(note) <= 140);
    ALTER TABLE strikes ADD COLUMN event_id INTEGER REFERENCES events(id) ON DELETE SET NULL;
    CREATE UNIQUE INDEX one_strike_per_meeting ON strikes(event_id, user_id) WHERE event_id IS NOT NULL;"""),
    # the server's own notes between starts: the achievements list the levels were last recorded for (Oct 6)
    (20, "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"),
    (21, "ALTER TABLE users ADD COLUMN mark TEXT;"),  # a person's mark by the name besides the Creator's: 'idea' (SPEC §1)
    (22, "ALTER TABLE org_roles ADD COLUMN rights TEXT;"),  # a club role's toggles, comma-separated; NULL: its level's (SPEC §2)
    # what the club asks DMP for in its weekly memo (Oct 11, PLAN "Memo in one tap"): JSON, the editor's "For the memo" block
    (23, "ALTER TABLE events ADD COLUMN memo TEXT;"),
    # the in-app room booking demo goes (Oct 11, owner's yes): DMP books rooms by memo (§4.12c)
    (24, "DROP TABLE IF EXISTS room_requests;"),
    # casting (PLAN "Casting", Oct 11): a club's recruitment round, its departments (the club's tags) and own questions, the
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
    # casting's interviews (Oct 11): the team's time slots (one by one, or a group: capacity), each shortlisted
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
    # a class's subject in ru / kk / en (JSON), so the schedule follows the app's language (owner, Oct 11)
    (27, "ALTER TABLE schedule_classes ADD COLUMN names TEXT;"),
    # the album (owner's list, Oct 10): a photo can be reported (the table gains 'photo' in its CHECK: rebuilt), and an event
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
    # memo v2 (PLAN stage 2, Oct 12): the sender's signature fixed once (JSON: nameEn, kk, ru, en), which events went to DMP,
    # who opened the week's memo last; the right "memo" (the secretary's), given to every club role that runs the team
    (29, """ALTER TABLE org_members ADD COLUMN memo_sign TEXT;
    ALTER TABLE events ADD COLUMN memo_sent_at INTEGER;
    ALTER TABLE events ADD COLUMN memo_sent_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    ALTER TABLE orgs ADD COLUMN memo_opened_at INTEGER;
    ALTER TABLE orgs ADD COLUMN memo_opened_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    UPDATE org_roles SET rights = rights || ',memo' WHERE ',' || rights || ',' LIKE '%,team,%';"""),
    # comment replies (PLAN "Comment replies", Oct 12): the comment answered, quoted above the reply; its author hears it
    (30, "ALTER TABLE comments ADD COLUMN reply_to INTEGER REFERENCES comments(id) ON DELETE SET NULL;"),
    # the admin's stats (PLAN "Admin stats", Oct 12): one row a day from users.seen_at, counts only, no per-person log
    (31, """CREATE TABLE stats_days (
        day INTEGER PRIMARY KEY,                -- days since 1970-01-01 in Almaty
        active INTEGER NOT NULL,                -- people who opened the app that day
        new INTEGER NOT NULL,                   -- people who opened it for the first time
        students INTEGER NOT NULL               -- signed in with KBTU by the day's end
    ) STRICT;"""),
    # badge skins (owner, Oct 13): the club whose badge I show; NULL = the KBTU one. Only an official club I'm in counts
    (32, "ALTER TABLE users ADD COLUMN skin_org INTEGER REFERENCES orgs(id) ON DELETE SET NULL;"),
    # the creator's one-time award link (owner, Oct 13: a bug report comes in a chat, not face to face)
    (33, """CREATE TABLE grant_links (
        token TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        used_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        used_at INTEGER
    ) STRICT;"""),
    # what I picked for my badge myself: NULL never (a new club's badge comes by itself, owner Oct 13), 'kbtu', 'org'
    # (skin_org), 'sower' (the creator's own)
    (34, """ALTER TABLE users ADD COLUMN skin_pick TEXT CHECK (skin_pick IN ('kbtu', 'org', 'sower'));
    UPDATE users SET skin_pick = 'org' WHERE skin_org IS NOT NULL;"""),
    # "delete my account" waits a week (owner, Oct 13: a change of heart shouldn't cost the awards): when it goes
    (35, "ALTER TABLE users ADD COLUMN delete_at INTEGER;"),
    # "First 500" for the cards 1-500 that never got it (owner Oct 14: "95%" with fewer than 500 people): the pilot
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
    # columns are Russian. Filled for KBTU's schools from kbtu.edu.kz (logic.seed_schools, owner Oct 14)
    (38, "ALTER TABLE orgs ADD COLUMN i18n TEXT;"),
    # an event's short vertical video (video.py, owner Oct 14): uploading in pieces -> queued -> working (the postman
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
    # the three official roles every club has (owner, Oct 15): President (the level, one per club), "Vice"
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
    # volunteers (owner, Oct 15): how many an event needs (NULL: none), maybe not year 1; applications the organizer decides
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
    # an event's Telegram group (owner, Oct 15, no userbot): the organizer adds the bot by a link carrying chat_token,
    # the bot keeps the group's id and its join-request link and lets in only those signed up
    (43, """ALTER TABLE events ADD COLUMN chat_id INTEGER;
    ALTER TABLE events ADD COLUMN chat_link TEXT;
    ALTER TABLE events ADD COLUMN chat_token TEXT;
    CREATE UNIQUE INDEX events_chat_token ON events(chat_token) WHERE chat_token IS NOT NULL;"""),
    # the events channel (owner, Oct 15): the post of a public event, and what it says (an edit when that changes)
    (44, """ALTER TABLE events ADD COLUMN channel_msg INTEGER;
    ALTER TABLE events ADD COLUMN channel_photo INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE events ADD COLUMN channel_sig TEXT;"""),
    # indoor routes (owner, Oct 15): the graph of corridors, stairs, lifts and exits he edits on the map; one row
    (45, """CREATE TABLE map_graph (id INTEGER PRIMARY KEY CHECK (id = 1), body TEXT NOT NULL, ver INTEGER NOT NULL,
    updated_by INTEGER, updated_at INTEGER NOT NULL);"""),
    # typed in by the student while the portal is out of reach (owner, Oct 16): replaced by the portal's data on their
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
    # an event's talk lives under its channel post in Telegram (owner, Oct 17): the link to the bot's first comment there
    (48, "ALTER TABLE events ADD COLUMN channel_link TEXT;"),
    # the KBTU-password sign-in is gone (owner, Oct 19): its wrong-password counter with it
    (49, "DROP TABLE IF EXISTS login_fails;"),
    # the KBTU Microsoft account a student signed in with (msauth.py): one account, one student
    (50, """ALTER TABLE students ADD COLUMN ms_oid TEXT;
        CREATE UNIQUE INDEX students_ms_oid ON students(ms_oid) WHERE ms_oid IS NOT NULL;"""),
    # everything Microsoft gives about the student, as it came (owner, Oct 20: "keep all we get, it's free"; the way
    # from typing it in to signing up by itself)
    (51, "ALTER TABLE students ADD COLUMN ms_profile TEXT;"),
    # a chat any student suggests through the bot waits for the admins (PLAN item 45, owner Oct 20); added_by is who
    (52, "ALTER TABLE chats ADD COLUMN status TEXT NOT NULL DEFAULT 'live';"),
    # departments (PLAN item 47, owner Oct 20): a tag marked as a department, one per person; a club's latest casting
    # round names its real ones (older rounds may hold tags that were never departments)
    (53, """ALTER TABLE org_tags ADD COLUMN department INTEGER NOT NULL DEFAULT 0;
        UPDATE org_tags SET department = 1 WHERE id IN (SELECT d.tag_id FROM round_departments d JOIN rounds r ON r.id = d.round_id
            WHERE r.id = (SELECT MAX(x.id) FROM rounds x WHERE x.org_id = r.org_id));"""),
    # a member link may put the newcomer straight into a department (PLAN 47: one who came by link landed in none)
    (54, "ALTER TABLE org_invites ADD COLUMN dept_id INTEGER REFERENCES org_tags(id) ON DELETE SET NULL;"),
]


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 15000")  # a write waits its turn: 600 sign-ups at once took 11 s on a laptop core (Oct 7)
    con.execute("PRAGMA synchronous = NORMAL")  # with WAL: no corruption on a crash, fsync only at checkpoints
    return con


class Pool:
    """Open connections kept for the next request. A new connection reads the whole schema before its first query
    (~4 ms on a laptop core, more than most requests take; load test, Oct 7); a kept one starts at once. A request
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
