"""The schema's changes after the base (schema.sql): MIGRATIONS, the steps db.init() runs on a database whose
user_version is behind, and the helpers only they use. Moved out of db.py as is (issue #21): the SQL is unchanged."""
from __future__ import annotations

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
    # Store socials by platform so the club's sheet can display each link.
    (3, "ALTER TABLE orgs ADD COLUMN links TEXT NOT NULL DEFAULT '[]'; UPDATE orgs SET links = json_array(link) WHERE link IS NOT NULL;"),
    # Keep recruitment open or closed at the club's discretion in Studio.
    (4, "ALTER TABLE orgs ADD COLUMN recruiting INTEGER NOT NULL DEFAULT 1; UPDATE orgs SET recruiting = 0 WHERE kind IN ('school','office','app');"
        " ALTER TABLE orgs DROP COLUMN recruiting_until;"),
    # the badge QR (§4.4): a random code per student, so nobody can make a QR from a user id;
    # walk_in marks a registration made at the door with that QR
    (5, "ALTER TABLE users ADD COLUMN qr_code TEXT; CREATE UNIQUE INDEX users_qr ON users(qr_code);"
        " ALTER TABLE registrations ADD COLUMN walk_in INTEGER NOT NULL DEFAULT 0;"),
    # Store a normalized focal point so tall, wide and square cover crops keep the same subject in view.
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
    # Store club-specific role names, colors and tags so club structure can vary without changing access levels.
    # Removal requests let a Head propose removal while leaving the decision to the President or a Vice.
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
    # Store wrong-password attempts so every worker applies the same five-attempt limit.
    # The partial indexes keep expired-hold and referral lookups from scanning all registrations.
    (17, """CREATE TABLE login_fails (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX login_fails_by_user ON login_fails(user_id, at);
    CREATE INDEX regs_holds ON registrations(hold_until) WHERE status = 'hold';
    CREATE INDEX regs_by_inviter ON registrations(invited_by) WHERE invited_by IS NOT NULL;"""),
    # Drop stored KBTU sessions to meet the retention rule in policy section 4.1.
    (18, "DROP TABLE IF EXISTS portal_sessions;"),
    # A team-only event lets a club record attendance for the whole team or one tag.
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
    # what the club asks DMP for in its weekly memo: JSON, the editor's "For the memo" block
    (23, "ALTER TABLE events ADD COLUMN memo TEXT;"),
    # DMP books rooms by memo (SPEC §4.12c).
    (24, "DROP TABLE IF EXISTS room_requests;"),
    # casting: a club's recruitment round, its departments (the club's tags) and own questions, the
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
    # Store the sender's signature so the club can reuse it across weekly memos.
    # Give the memo permission to roles that manage the club's team.
    (29, """ALTER TABLE org_members ADD COLUMN memo_sign TEXT;
    ALTER TABLE events ADD COLUMN memo_sent_at INTEGER;
    ALTER TABLE events ADD COLUMN memo_sent_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    ALTER TABLE orgs ADD COLUMN memo_opened_at INTEGER;
    ALTER TABLE orgs ADD COLUMN memo_opened_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    UPDATE org_roles SET rights = rights || ',memo' WHERE ',' || rights || ',' LIKE '%,team,%';"""),
    # comment replies: the comment answered, quoted above the reply; its author hears it
    (30, "ALTER TABLE comments ADD COLUMN reply_to INTEGER REFERENCES comments(id) ON DELETE SET NULL;"),
    # the admin's stats: one row a day from users.seen_at, counts only, no per-person log
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
    # Backfill missing First 500 grants by card number without sending award notifications.
    (36, """INSERT INTO achievement_grants (user_id, code, note, created_at)
        SELECT u.id, 'first50', 'backfill', CAST(strftime('%s', 'now') AS INTEGER) FROM users u JOIN students s ON s.user_id = u.id
        WHERE s.consent_version != 'staff' AND (u.is_founder = 1 OR u.card_no <= 500)
        AND NOT EXISTS (SELECT 1 FROM achievement_grants g WHERE g.user_id = u.id AND g.code = 'first50');
    INSERT INTO achievement_levels (user_id, code, level, reached_at, seen)
        SELECT g.user_id, 'first50', 1, g.created_at, 1 FROM achievement_grants g WHERE g.code = 'first50' AND g.note = 'backfill' AND true
        ON CONFLICT (user_id, code) DO UPDATE SET level = MAX(level, 1);"""),
    # Use Telegram metadata so directory cards match the chats. Keep the topics flag so the UI can distinguish them.
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
    # Track club role history with triggers so every membership write records joins, leaves and role changes.
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
    # The password counter can be dropped because Microsoft handles authentication.
    (49, "DROP TABLE IF EXISTS login_fails;"),
    # the KBTU Microsoft account a student signed in with (msauth.py): one account, one student
    (50, """ALTER TABLE students ADD COLUMN ms_oid TEXT;
        CREATE UNIQUE INDEX students_ms_oid ON students(ms_oid) WHERE ms_oid IS NOT NULL;"""),
    # Store the Microsoft profile as returned so sign-in can use the directory fields to prefill the student record.
    (51, "ALTER TABLE students ADD COLUMN ms_profile TEXT;"),
    # Mark student suggestions as pending so they stay out of the directory until an admin approves them.
    (52, "ALTER TABLE chats ADD COLUMN status TEXT NOT NULL DEFAULT 'live';"),
    # Use tags from the latest casting round to identify departments because older rounds may refer to other tags.
    (53, """ALTER TABLE org_tags ADD COLUMN department INTEGER NOT NULL DEFAULT 0;
        UPDATE org_tags SET department = 1 WHERE id IN (SELECT d.tag_id FROM round_departments d JOIN rounds r ON r.id = d.round_id
            WHERE r.id = (SELECT MAX(x.id) FROM rounds x WHERE x.org_id = r.org_id));"""),
    # Carry the department on the member link so a newcomer can be placed without a second Studio action.
    (54, "ALTER TABLE org_invites ADD COLUMN dept_id INTEGER REFERENCES org_tags(id) ON DELETE SET NULL;"),
    # Record the media slot on upload because the carousel and sheet background need different compression.
    (55, """CREATE TABLE event_slides (
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      pos      INTEGER NOT NULL,
      file_id  INTEGER NOT NULL REFERENCES files(id),
      PRIMARY KEY (event_id, pos)
    ) STRICT;
    ALTER TABLE events ADD COLUMN wide_video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL;
    ALTER TABLE videos ADD COLUMN wide INTEGER NOT NULL DEFAULT 0;"""),
    # texts in three languages by AI: i18n holds the other two languages, lang the source's (NULL: to
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
    # Derive the year from the ID only for self-reported records. A repeater's portal year can differ from the ID's intake.
    (58, """UPDATE students SET course = MAX(1, MIN(6, CAST(strftime('%Y', 'now', '+5 hours') AS INTEGER)
        - (CAST(strftime('%m', 'now', '+5 hours') AS INTEGER) < 9) - (2000 + CAST(substr(student_id, 1, 2) AS INTEGER)) + 1))
      WHERE consent_at >= 1792350000 AND student_id GLOB '[0-9][0-9][A-Z]*' AND consent_version NOT IN ('staff', 'admin');"""),
    # Assign missing card numbers in sign-in order after the highest number issued so numbers are never reused.
    (59, """UPDATE users SET card_no = r.base + r.n FROM (SELECT s.user_id,
            ROW_NUMBER() OVER (ORDER BY s.verified_at, s.user_id) AS n,
            MAX((SELECT COALESCE(MAX(card_no), 0) FROM users),
                (SELECT COALESCE(MAX(CAST(value AS INTEGER)), 0) FROM meta WHERE key = 'card_last')) AS base
          FROM students s JOIN users x ON x.id = s.user_id
          WHERE x.card_no IS NULL AND x.is_founder = 0 AND x.tg_id > 0 AND s.manual = 0 AND s.consent_version != 'staff') r
        WHERE r.user_id = users.id;
      INSERT INTO meta (key, value) SELECT 'card_last', MAX(card_no) FROM users WHERE card_no IS NOT NULL HAVING MAX(card_no) IS NOT NULL
        ON CONFLICT (key) DO UPDATE SET value = MAX(CAST(value AS INTEGER), CAST(excluded.value AS INTEGER));"""),
    (60, "DROP TABLE strikes; DELETE FROM bot_outbox WHERE kind = 'strike';"),
    # Reset non-founder admin roles to prevent stale privileges. Accounts in ADMIN_TG_IDS regain the role at sign-in.
    (61, "UPDATE users SET role = 'user' WHERE role = 'admin' AND is_founder = 0;"),  # the owner never loses it
    # Store the academic year for which the course is valid so it can advance each September 1.
    # Cap courses inferred from self-reported IDs at the length of the degree and preserve portal-verified years.
    (62, """ALTER TABLE students ADD COLUMN course_year INTEGER;
    UPDATE students SET course_year = MAX(CAST(strftime('%Y', synced_at, 'unixepoch', '+5 hours') AS INTEGER)
        - (CAST(strftime('%m', synced_at, 'unixepoch', '+5 hours') AS INTEGER) < 9),
        CASE WHEN student_id GLOB '[0-9][0-9][A-Z]*' THEN 2000 + CAST(substr(student_id, 1, 2) AS INTEGER) ELSE 0 END)
      WHERE course IS NOT NULL;
    UPDATE students SET course = CASE substr(student_id, 3, 1) WHEN 'B' THEN 4 ELSE 2 END
      WHERE synced_at >= 1792350000 AND consent_version NOT IN ('staff', 'admin')
        AND ((student_id GLOB '[0-9][0-9]B*' AND course > 4) OR (student_id GLOB '[0-9][0-9]M*' AND course > 2));"""),
    # Track daily stranger-profile opens for rate limits (logic._stranger_view). Keep them at most two days.
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
    # Keep existing application answers when rebuilding for social links.
    # Store unclaimed walk-ins so they can count after Microsoft verifies a matching student (logic.ms_link).
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
    # Default recruitment to closed so the list shows only clubs that opt in. Casting rounds can appear independently.
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
    # Ask for a phone number only at events that need one and reuse the saved number at later sign-ups.
    (69, "ALTER TABLE events ADD COLUMN needs_phone INTEGER NOT NULL DEFAULT 0;"),
    # Keep abbreviations for surfaces where the full name will not fit. logic.fill_abbrs supplies missing initials
    # because SQLite cannot uppercase Cyrillic.
    (70, "ALTER TABLE orgs ADD COLUMN abbr TEXT;"),
    # Chats on a club's or school's page need an org_id to identify the club that manages them.
    # main = its one channel with the Subscribe button and the mirror source. about = the chat description. A chat
    # linked only from Studio waits as status 'org', out of the shared catalog
    (71, """ALTER TABLE chats ADD COLUMN org_id INTEGER REFERENCES orgs(id) ON DELETE SET NULL;
    ALTER TABLE chats ADD COLUMN main INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE chats ADD COLUMN about TEXT;
    CREATE INDEX chats_by_org ON chats(org_id);
    CREATE UNIQUE INDEX chats_main ON chats(org_id) WHERE main = 1;"""),
    # Mirror a club's main public channel into its news (userbot.py, mirror.py).
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
    # Keep imported club roster rows separate until the student's identity can be checked.
    # joined at once when the Telegram username (or e-mail) AND the name match the KBTU account (roster.py), asked when
    # only the username does; claimed_by: "Yes, it's me" anyway, waiting for the club's President (or DMP); rejected_by:
    # declined by them, kept for the right person. users.city comes from the roster and can be hidden or deleted.
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
    # Keep each side's contact decision so sharing can require both students to agree.
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
    # referrals: who brought me, by their invite link (r_<badge code>); the first link wins.
    (77, """ALTER TABLE users ADD COLUMN referred_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    CREATE INDEX users_by_referrer ON users(referred_by) WHERE referred_by IS NOT NULL;"""),
    # Cache Telegram photos so opening a profile does not wait on t.me. src identifies the cached source URL.
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
    # Show a partner's event with the partner's name and external link so it does not issue app tickets or count as the club's own.
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
    # Store an anonymous thread author solely for the admin's audited reveal.
    # Rebuild the reports table because SQLite cannot alter its target CHECK.
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
    # Keep event-specific questions as JSON [{label, kind text|choice, options, required}].
    # the answers on the registration, JSON [{q, a}] (the question's words as they were), wiped 30 days after the event
    (86, "ALTER TABLE events ADD COLUMN questions TEXT; ALTER TABLE registrations ADD COLUMN answers TEXT;"),
    # Store the map version, floor and coordinates so staff can locate a reported flaw without a screenshot.
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
    # Track the check-in phase and last exit scan so attendance can show who left and when.
    (89, "ALTER TABLE qr_sessions ADD COLUMN phase TEXT NOT NULL DEFAULT 'in' CHECK (phase IN ('in', 'out')); ALTER TABLE qr_marks ADD COLUMN left_at INTEGER;"),
    # Give published links a separate code so sharing a link never reveals the badge secret.
    # Preserve existing links by retaining their codes for links and issuing fresh badge secrets.
    (90, """ALTER TABLE users ADD COLUMN link_code TEXT;
    UPDATE users SET link_code = qr_code, qr_code = NULL WHERE qr_code IS NOT NULL;
    CREATE UNIQUE INDEX users_link ON users(link_code);"""),
    # Keep campus facts editable by moderators so they can correct stale locations without a deploy.
    # Seed the known English names with verified_at NULL so unverified entries remain identifiable.
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
    # Keep assistant feedback anonymous. Store the model's short topic for a question it
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
    # Key imported freshmen rows by KBTU email so each row is shown only to
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
    # or as the student typed it in My data. Use a known spelling in English UI and exports
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
    # Store the terms clause with a removed comment so the verdict can give the reason.
    (101, """ALTER TABLE tgc_comments ADD COLUMN clause TEXT CHECK (clause IN ('abuse', 'fake', 'spam', 'pdata', 'disrupt', 'other'));
    UPDATE tgc_comments SET clause = CASE rule WHEN 'spam' THEN 'spam' WHEN 'other' THEN 'other' ELSE 'abuse' END WHERE rule IS NOT NULL;"""),
    # the forum channel (FORUM_CHANNEL, logic/fchannel.py): a student's post, published by the bot after the AI's
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
    # Clear unused in-app forum data so retired threads, reactions, reports and unsent notices are no longer retained.
    (103, """DELETE FROM thread_joins; DELETE FROM thread_replies; DELETE FROM threads;
    DELETE FROM reports WHERE target IN ('thread', 'reply');
    DELETE FROM bot_outbox WHERE kind = 'thread_reply';"""),
    # a replaced receipt's fingerprint: the duplicate check still sees it, and it counts toward the
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
    # Track the first bot comment per channel message to avoid duplicate rules and give the app a link into the thread.
    # Count the student comments the bot sees because the Bot API has no comment count.
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
    # Group the directory by what each chat is for so students can browse by purpose.
    # The AI classifies public titles and descriptions. Keep its decision marked until staff check it and delay failed retries an hour.
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
    # a forum post's card mirrors Telegram: the faces of the app's students who commented (one row per comment
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
    # Keep club-written next steps in the app so recruitment instructions can vary while bot notifications stay templated.
    (108, "ALTER TABLE rounds ADD COLUMN next_text TEXT NOT NULL DEFAULT '' CHECK (length(next_text) <= 300);"),
    # Index only waiting messages so bot._due can poll without scanning failed rows.
    (109, "CREATE INDEX IF NOT EXISTS outbox_todo ON bot_outbox(send_after, id) WHERE sent_at IS NULL AND error IS NULL;"),
    # Index the join-request, pinned-feed and event-date queries that run on list views.
    (110, """CREATE INDEX IF NOT EXISTS join_requests_by_user ON join_requests(user_id);
    CREATE INDEX IF NOT EXISTS posts_feed ON posts(audience, pinned, created_at);
    CREATE INDEX IF NOT EXISTS events_by_start ON events(starts_at);"""),
    # a club's member link for the whole team (logic.team_link): many join by it as plain members, 7 days, one per club
    (111, "ALTER TABLE org_invites ADD COLUMN multi INTEGER NOT NULL DEFAULT 0;"),
    # a frame drawn over my photo on the lanyard, picked apart from the lanyard itself (logic.FRAMES)
    (112, "ALTER TABLE users ADD COLUMN frame TEXT;"),
    # the stranger's message his warning was for: the same update again after a restart is not a second comment
    (113, "ALTER TABLE tgc_strangers ADD COLUMN warned_msg INTEGER;"),
    # a forum channel post reported from the feed ('fpost', logic/moderation.py): the CHECK takes the new kind.
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
    # "Can add me as a friend": off, nobody can send me a request; friends and waiting requests stay
    (115, "ALTER TABLE users ADD COLUMN can_friend INTEGER NOT NULL DEFAULT 1;"),
    # Record the original school so a student can undo an accidental correction without spending another change.
    (116, "ALTER TABLE students ADD COLUMN once_was TEXT NOT NULL DEFAULT '{}';"),
    # an anonymous post's author answers in its comments through the bot.
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
    # Admin → Awards: a grant's batch, undone at once: a scanner run ('s_…'), a link's people ('l_<token>'), a
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
    # Admin → Inbox: decided() and Undo read a thing's newest line, Done the last 30 days
    (119, """CREATE INDEX IF NOT EXISTS audit_by_target ON audit_log(target, id);
    CREATE INDEX IF NOT EXISTS audit_by_at ON audit_log(at);"""),
    # late sign-up: a free uncapped public event keeps "Going" open from its start until its end
    (120, "ALTER TABLE events ADD COLUMN late_signup INTEGER NOT NULL DEFAULT 0;"),
    # an anonymous post's random nick: texts.NICK_ADJ / NICK_NOUN indexes,
    # drawn with secrets at the reserve; NULL on posts from before (signed "Anon")
    (121, """ALTER TABLE fchan_posts ADD COLUMN nick_a INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN nick_n INTEGER;"""),
    # A host can list one co-host after that club's Vice+ accepts (logic/cohosts.py).
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
    # a forum post the AI refused (noise, an ad) that its author sent to a moderator (fchannel.appeal): when, for
    # the day's three; explained: the AI's reason for a refusal was asked (once a post or reply: ai.explain); refused: a
    # hash of the refused words (they're wiped), so the appeal and the reason are only ever about the words the AI read
    (123, """ALTER TABLE fchan_posts ADD COLUMN appealed_at INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN refused TEXT;
    ALTER TABLE fchan_posts ADD COLUMN explained INTEGER;
    ALTER TABLE fchan_replies ADD COLUMN explained INTEGER;"""),
    # the AI's reason (ai.explain's validated sentence) kept on the row, so a moderator deciding on a held or appealed
    # post or reply reads why the AI stopped it. Delete the reason with the row.
    (124, """ALTER TABLE fchan_posts ADD COLUMN ai_reason TEXT;
    ALTER TABLE fchan_replies ADD COLUMN ai_reason TEXT;"""),
    # the path to the official ✓: a student initiative that did the five steps asks the admin (logic/clubs.py,
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
    # Keep an official club's "Don't suggest again" response so an initiative cannot keep asking to co-host.
    # Track the co-host whose official status permits an initiative's event in the channel (NULL: the host's own
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
    # always-open recruitment: the club's own questions for any-time join requests (JSON, as a
    # round's: kind, text, options, required) and each request's answers (JSON [{q, a}], the question's text kept with it)
    (131, "ALTER TABLE orgs ADD COLUMN join_questions TEXT; ALTER TABLE join_requests ADD COLUMN answers TEXT;"),
    # the Ascent (logic/clubs.py): when a student initiative reached the top, kept once reached (an
    # official club's tools without the ✓)
    (132, "ALTER TABLE orgs ADD COLUMN top_at INTEGER;"),
    # Track results per applicant so clubs can send them in batches without duplicates. Backfill sent_at for completed rounds.
    # Keep the optional Telegram invite in the app so only accepted applicants see it.
    (133, """ALTER TABLE round_apps ADD COLUMN sent_at INTEGER;
    ALTER TABLE rounds ADD COLUMN group_link TEXT;
    UPDATE round_apps SET sent_at = (SELECT r.sent_at FROM rounds r WHERE r.id = round_apps.round_id)
        WHERE stage != 'withdrawn' AND round_id IN (SELECT id FROM rounds WHERE status = 'done');"""),
    # Admin → Awards → Show QR: a grant link shown as a rotating code on the giver's phone (qr = 1),
    # used only through a fresh signed code (profiles.claim_qr), never by its bare token, and only while the screen
    # keeps renewing its lease (lease_until: a killed or offline screen stops the code within seconds)
    (134, "ALTER TABLE grant_links ADD COLUMN qr INTEGER NOT NULL DEFAULT 0; ALTER TABLE grant_links ADD COLUMN lease_until INTEGER;"),
    # the host club's own people are never its guests: their seats at its upcoming public events go back
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
    # the 3rd years' answer under the incubator's elective post (admin announce3): more like it? NULL: never asked
    (136, "ALTER TABLE users ADD COLUMN announce_ok INTEGER;"),
    # the door opened early by the club's President or a Vice (organizing.open_door); NULL: at T-30 by itself (core.door_at)
    # Preserve access for doors already open at migration time so guests can still enter.
    (137, """ALTER TABLE events ADD COLUMN door_open_at INTEGER;
    UPDATE events SET door_open_at = starts_at - 10800 WHERE status = 'published' AND starts_at - 10800 <= CAST(strftime('%s', 'now') AS INTEGER)
      AND CAST(strftime('%s', 'now') AS INTEGER) < starts_at - 1800 AND EXISTS (SELECT 1 FROM registrations r WHERE r.event_id = events.id AND r.checked_in_at IS NOT NULL);"""),
    # Store approval per member and event so seats.joined can preserve a seat that a President or Vice granted.
    (138, """CREATE TABLE team_asks (
      event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','yes','no')),
      created_at INTEGER NOT NULL,
      decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      decided_at INTEGER,
      PRIMARY KEY (event_id, user_id)
    ) STRICT;"""),
    (139, "UPDATE events SET album_open = 1 WHERE album_open = 0;"),
    # Prefix the four-character ticket code with its event ID so the existing UNIQUE constraint enforces per-event uniqueness.
    # Retry collisions with OR IGNORE. The status CHECK rolls back the migration if any code remains unset after eight passes.
    (140, "UPDATE registrations SET ticket_code = 'old:' || id;\n" + "\n".join([
        """UPDATE OR IGNORE registrations SET ticket_code = event_id || '-' || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1)
          || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1) || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1)
          || substr('23456789ABCDEFGHJKMNPQRSTUVWXYZ', 1 + abs(random() % 31), 1) WHERE ticket_code GLOB 'old:*';"""] * 8)
     + "\nUPDATE registrations SET status = 'unset' WHERE ticket_code GLOB 'old:*';"),
    # Drop Sunday classes because the portal lists duplicate online copies of weekday classes.
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
    # (checkin.mark). NULL lets a session survive a deploy until the next poll establishes its lease.
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
    # the Gallery (logic/gallery.py): a photo a student posted under their name, of KBTU or of an event they went
    # to (that one is in its album too, event_photos).
    # Rebuild the reports table to allow separate reports for rule violations and objection to appearing in a photo.
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
    # Re-encode forum photos and randomize their names so uploads carry neither EXIF nor the original filename.
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
    # Display publication time so a held anonymous post does not reveal when it was written.
    # Keep the AI tip and excerpt with the reason so the author can see them after a reload.
    (153, """ALTER TABLE fchan_posts ADD COLUMN posted_at INTEGER;
    ALTER TABLE fchan_posts ADD COLUMN ai_fix TEXT;
    ALTER TABLE fchan_posts ADD COLUMN ai_quote TEXT;"""),
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
    # Use a nullable topic on gallery_photos so standalone photos can be categorized without a table rebuild.
    # An uncategorized standalone photo reads as Other.
    (157, "ALTER TABLE gallery_photos ADD COLUMN topic TEXT CHECK (topic IN ('campus', 'study', 'life', 'other'));"),
    # a club's report after its event (logic/evreports.py, REPORTS=1): which department ran it (a tag marked
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
    # event reports' own consent (evreports.CONSENT, as appeal_consents): one per person, for every club; no
    # row, no report of mine and no mark of me
    (159, """CREATE TABLE report_consents (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      version TEXT NOT NULL,
      at INTEGER NOT NULL) STRICT;"""),
    # a report per club: the host and its accepted co-host each write their own (evreports.py). 158's tables
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
    # team events (logic/evteams.py): a free event's teams of team_min..team_max people (NULL: not a team
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
    # an album in the order its photos were taken: the time from the upload's EXIF (media.taken; the one fact
    # kept of it), unix seconds with the camera's sub-seconds; NULL (no EXIF, or uploaded before): its upload time
    (162, "ALTER TABLE files ADD COLUMN taken_at REAL;"),
    # a check-in marked by hand from the student's badge QR (checkin.badge): who marked it
    (163, "ALTER TABLE qr_marks ADD COLUMN marked_by INTEGER REFERENCES users(id) ON DELETE SET NULL;"),
    # a club's group moderated for swearing (logic/chatmod.py): chats.swear is its switch, off by default. A hit
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
    # /all calls who the bot saw in a club's chat too (Telegram gives bots no member list): Telegram ids
    # alone, no names or words, with the club that held the chat then; forgotten on leaving, with the chat, as soon
    # as another club or none holds it (triggers: every way a link changes), and 180 days after they were last seen
    (165, _CHAT_SEEN),
    # a club's team marked at one of its events (checkin.crew): a club session tied to the event, apart from
    # its guests' session (event_id); one per event; the event deleted, the attendance stays
    (166, """ALTER TABLE qr_sessions ADD COLUMN crew_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL;
    CREATE UNIQUE INDEX qr_sessions_by_crew ON qr_sessions(crew_event_id) WHERE crew_event_id IS NOT NULL;"""),
    # "Solved by your appeals" (appeals.solved): SG's public lines, what students raised and what changed. No
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
    # a school's own event only for its students (seats._visible): the school's slug, NULL for everyone
    (168, "ALTER TABLE events ADD COLUMN school TEXT;"),
    # a chat our bot was made admin in, no club holding it, remembered for the one who did it (Telegram's
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
    # /all in a chat no club holds: whom the bot saw there, Telegram ids only (chat_seen without a club)
    (170, """CREATE TABLE chat_seen_free (
      chat_id INTEGER NOT NULL,
      tg_id INTEGER NOT NULL,
      seen_at INTEGER NOT NULL,
      PRIMARY KEY (chat_id, tg_id)) STRICT, WITHOUT ROWID;"""),
    # whom an event's door records: guests, its team, or both (NULL: both, the team routed by
    # membership in checkin._team). Preserve team-only check-in for event 34.
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
    # a hand mark is told apart from a scan and a badge by itself, not by who marked (marked_by goes
    # NULL with the marker's account): 1 the row is the hand mark's, 2 a scan waiting for its sign-up completed by hand.
    # A team list's hand mark with no account goes with its row (a roster row joined or deleted, an expected row of a
    # deleted account: the key carries the mail)
    (172, """ALTER TABLE qr_marks ADD COLUMN hand INTEGER NOT NULL DEFAULT 0;
    CREATE TRIGGER qr_hand_roster_gone AFTER DELETE ON roster_pending BEGIN
      DELETE FROM qr_hand_marks WHERE who = 'r' || old.id;
    END;
    CREATE TRIGGER qr_hand_expected_gone AFTER DELETE ON qr_expected BEGIN
      DELETE FROM qr_hand_marks WHERE session_id = old.session_id AND who = 'x' || old.email;
    END;"""),
    # the help desk beside SG's (logic/appeals.py, ASK): questions KRI couldn't answer, handed to a person; its
    # own people and its own consent (appeal_consents holds one version a person: a table of its own, not a row there)
    (173, """ALTER TABLE appeals ADD COLUMN desk TEXT NOT NULL DEFAULT 'sg' CHECK (desk IN ('sg', 'help'));
    CREATE TABLE help_staff (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      at INTEGER NOT NULL) STRICT;
    CREATE TABLE help_consents (
      user_id INTEGER PRIMARY KEY REFERENCES users(id),
      version TEXT NOT NULL,
      at INTEGER NOT NULL) STRICT;"""),
    # each desk its own day's count: three questions to a person never block an appeal to SG
    (174, """ALTER TABLE appeal_sends ADD COLUMN desk TEXT NOT NULL DEFAULT 'sg';"""),
    # paid team events (evteams.py): an event's cap on the number of teams (NULL: no cap); a paid seat on hold
    # keeps the invite token it came by until the receipt is in (then joined if there's room), '-' once it missed
    (175, """ALTER TABLE events ADD COLUMN team_cap INTEGER;
    ALTER TABLE registrations ADD COLUMN team_want TEXT;
    CREATE TRIGGER event_team_want_done AFTER INSERT ON event_team_members BEGIN
      UPDATE registrations SET team_want = NULL WHERE event_id = NEW.event_id AND user_id = NEW.user_id AND team_want IS NOT NULL;
    END;"""),
    # the tree of a club's groups (logic/chattree.py): where its Vice+ placed a group the sync doesn't hold;
    # a label only (never a sync link), counted while the group is still that club's
    (176, """CREATE TABLE chat_place (
      chat_id INTEGER PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      place TEXT NOT NULL CHECK (place IN ('main', 'dept', 'other')),
      tag_id INTEGER REFERENCES org_tags(id) ON DELETE CASCADE,
      at INTEGER NOT NULL,
      CHECK ((place = 'dept') = (tag_id IS NOT NULL))) STRICT;"""),
    # the subjects' cards (logic/subjects.py): "looking for people to study it with" is a find-people request
    # on a subject (its card's id), one per person and subject; the requests' moderation, contact and expiry as they are
    # Give each offer a token so a button cannot reveal a student's Telegram handle through a reused offer ID.
    # Assign tokens to stored offers as well so tokenless buttons cannot act on them.
    (177, """ALTER TABLE asks ADD COLUMN subject TEXT;
    CREATE UNIQUE INDEX asks_subject ON asks(subject, user_id) WHERE subject IS NOT NULL;
    ALTER TABLE contacts ADD COLUMN token TEXT;
    UPDATE contacts SET token = lower(hex(randomblob(16))) WHERE token IS NULL;
    -- a moderator's take-down of a subject listing, apart from the listing (logic/subjects.py): one per author and
    -- subject; while it stands (until the listing's own end) the listing is out of sight and listing again is refused;
    -- lifting deletes it (Done's Undo makes it again). Ids never come back (AUTOINCREMENT): a stale tap only misses
    CREATE TABLE subject_holds (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      subject TEXT NOT NULL,
      title TEXT NOT NULL,
      by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      why TEXT NOT NULL,
      at INTEGER NOT NULL,
      until INTEGER NOT NULL,
      UNIQUE (user_id, subject)) STRICT;
    -- asks and contacts never hand a deleted row's id to the next one (core.next_id; a rebuild for AUTOINCREMENT is
    -- not allowed): their high-water marks from here on
    INSERT OR REPLACE INTO meta (key, value) SELECT 'seq:asks', CAST(COALESCE(MAX(id), 0) AS TEXT) FROM asks;
    INSERT OR REPLACE INTO meta (key, value) SELECT 'seq:contacts', CAST(COALESCE(MAX(id), 0) AS TEXT) FROM contacts;"""),
    # the creator's word that this Telegram account is KBTU staff (an office's own: DMP), never a student
    # (kbtu.admin staff-ok): its Microsoft sign-in asks no student ID (account.staff_ok); nothing in the app grants it
    (178, """CREATE TABLE IF NOT EXISTS staff_ok (  -- IF NOT EXISTS: tests rewind user_version to rerun older ones
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      granted_at INTEGER NOT NULL) STRICT;"""),
    # An open interview slot admits everyone during its time window. round_slots' CHECKs cap a slot at
    # 180 minutes and 50 people and cannot be altered, so the real
    # span lives here and the slot's row keeps the caps as stand-ins (casting._mins, _cap)
    (179, """CREATE TABLE IF NOT EXISTS round_wide (  -- IF NOT EXISTS: tests rewind user_version
      slot_id INTEGER PRIMARY KEY REFERENCES round_slots(id) ON DELETE CASCADE,
      minutes INTEGER NOT NULL CHECK (minutes BETWEEN 5 AND 840)) STRICT;"""),
    # events found in a club's channel (logic/autoev.py): each mirrored post looked at once, the draft it made
    (180, """CREATE TABLE IF NOT EXISTS auto_events (  -- IF NOT EXISTS: tests rewind user_version
      post_id  INTEGER PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
      org_id   INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,  -- NULL: no event in it, or its draft deleted (never proposed again)
      at       INTEGER NOT NULL) STRICT;
    CREATE INDEX IF NOT EXISTS auto_events_org ON auto_events(org_id, at);
    CREATE INDEX IF NOT EXISTS auto_events_event ON auto_events(event_id);"""),
    # Secret Santa on an event (logic/santa.py): the editor's switch and when it was drawn; who plays, their
    # wishlist (kept here, not in registrations.answers: the organizers read those) and, after the draw, whom they give
    # to. gives_to has no row of its own on purpose: a pair is read through its giver alone.
    (181, """CREATE TABLE IF NOT EXISTS santa_events (  -- IF NOT EXISTS: tests rewind user_version
      event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
      drawn_at INTEGER) STRICT;
    CREATE TABLE IF NOT EXISTS santa_people (
      event_id INTEGER NOT NULL REFERENCES santa_events(event_id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      wish TEXT NOT NULL,
      gives_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
      PRIMARY KEY (event_id, user_id)) STRICT, WITHOUT ROWID;
    CREATE INDEX IF NOT EXISTS santa_people_user ON santa_people (user_id);
    CREATE INDEX IF NOT EXISTS santa_people_to ON santa_people (gives_to);"""
     # a seat lost any way (cancelled, removed, a rejected receipt, the row deleted) takes the person out of the game
     # for good, in the same transaction: their Santa gives to their person, their row goes. A seat given back later
     # (a walk-in at the door) brings no Santa membership back, so a relink is never undone
     + "".join(f"""
    CREATE TRIGGER IF NOT EXISTS santa_left_{name} AFTER {op} ON registrations WHEN OLD.status = 'going'{when} BEGIN
      UPDATE santa_people SET gives_to = (SELECT gives_to FROM santa_people WHERE event_id = OLD.event_id AND user_id = OLD.user_id)
        WHERE event_id = OLD.event_id AND gives_to = OLD.user_id;
      DELETE FROM santa_people WHERE event_id = OLD.event_id AND user_id = OLD.user_id;
    END;""" for name, op, when in (("upd", "UPDATE OF status, user_id", " AND (NEW.status != 'going' OR NEW.user_id != OLD.user_id)"), ("del", "DELETE", "")))),
    # KBTU Awards: the nominations a club won at the university's yearly ceremony, on its card (clubs.awards)
    (182, """CREATE TABLE IF NOT EXISTS org_awards (  -- IF NOT EXISTS: tests rewind user_version
      org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
      year INTEGER NOT NULL,
      title TEXT NOT NULL,  -- the nomination's English name as the ceremony gives it
      created_at INTEGER NOT NULL,
      PRIMARY KEY (org_id, year, title)) STRICT;"""),
    # an event's one document (its rules, a PDF): kept as its pages' pictures under media/, never the PDF (organizing.put_doc)
    (183, """CREATE TABLE IF NOT EXISTS event_docs (  -- IF NOT EXISTS: tests rewind user_version
      event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
      title TEXT,
      pages TEXT NOT NULL,
      created_at INTEGER NOT NULL) STRICT;"""),
    # Secret Santa (logic/santa.py): the game's settings beside its row (the gift budget; the wishlists'
    # deadline is the event's own reg_until) and the bot round's marks, so each timed step runs once: `checked` the
    # deadline already acted on (a moved one re-arms itself), `soon` the eve-of-deadline reminder, `eve` and `late` the
    # gifts day each was sent for (a moved day re-arms them), `nudged_at` the organizer's last "remind those not in yet".
    # No user column: nothing here names a person.
    (184, """CREATE TABLE IF NOT EXISTS santa_games (  -- IF NOT EXISTS: tests rewind user_version
      event_id INTEGER PRIMARY KEY REFERENCES santa_events(event_id) ON DELETE CASCADE,
      budget INTEGER CHECK (budget IS NULL OR budget > 0),
      checked INTEGER,
      soon INTEGER,
      eve INTEGER,
      late INTEGER,
      nudged_at INTEGER) STRICT;
    INSERT OR IGNORE INTO santa_games (event_id) SELECT event_id FROM santa_events;  -- the games already running
    -- a running game from before deadlines (none set): santa.default_until's, a week before the gifts day (halfway when
    -- closer, an hour before it at the latest), so it draws by itself; due within a day: no "closes tomorrow" burst
    UPDATE events SET reg_until = MIN(starts_at - 3600, CASE WHEN starts_at - 604800 > CAST(strftime('%s', 'now') AS INTEGER) THEN starts_at - 604800
        ELSE CAST(strftime('%s', 'now') AS INTEGER) + (starts_at - CAST(strftime('%s', 'now') AS INTEGER)) / 2 END)
      WHERE reg_until IS NULL AND late_signup = 0 AND status = 'published' AND starts_at > CAST(strftime('%s', 'now') AS INTEGER) + 3600
        AND id IN (SELECT event_id FROM santa_events WHERE drawn_at IS NULL);
    UPDATE santa_games SET soon = CAST(strftime('%s', 'now') AS INTEGER) WHERE event_id IN (SELECT id FROM events WHERE reg_until < CAST(strftime('%s', 'now') AS INTEGER) + 86400);
    -- a running game whose deadline already passed undrawn (closed by hand before this round): no draw out of the blue;
    -- its President hears once that it waits for them (santa_wait), and a new deadline re-arms it
    INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, payload, send_after)
      SELECT m.user_id, 'santa_wait', 'event:' || e.id, '{}', CAST(strftime('%s', 'now') AS INTEGER) FROM events e JOIN santa_events s ON s.event_id = e.id AND s.drawn_at IS NULL
        JOIN org_members m ON m.org_id = e.org_id AND m.role = 'president'
        WHERE e.status = 'published' AND e.reg_until <= CAST(strftime('%s', 'now') AS INTEGER) AND e.starts_at > CAST(strftime('%s', 'now') AS INTEGER);
    UPDATE santa_games SET checked = (SELECT reg_until FROM events WHERE id = santa_games.event_id)
      WHERE event_id IN (SELECT e.id FROM events e JOIN santa_events s ON s.event_id = e.id AND s.drawn_at IS NULL
        WHERE e.reg_until <= CAST(strftime('%s', 'now') AS INTEGER));"""
     # a seat lost after the draw (before the relink, santa_left_*, moves the ring): with three or more left, its Santa
     # hears once that their person changed; with two left, both hear they give to each other (each knows it anyway);
     # with one left, they hear the game is over for them; a "wishlist updated" still queued for that Santa goes (it was
     # someone else's). Refs carry the event and a random tag, never the leaver
     + "".join(f"""
    CREATE TRIGGER IF NOT EXISTS santa_moved_{name} BEFORE {op} ON registrations WHEN OLD.status = 'going'{when}
        AND EXISTS (SELECT 1 FROM santa_events WHERE event_id = OLD.event_id AND drawn_at IS NOT NULL)
        AND EXISTS (SELECT 1 FROM santa_people WHERE event_id = OLD.event_id AND user_id = OLD.user_id) BEGIN
      DELETE FROM bot_outbox WHERE kind = 'santa_wish' AND sent_at IS NULL AND ref LIKE 'event:' || OLD.event_id || ':%'
        AND user_id IN (SELECT user_id FROM santa_people WHERE event_id = OLD.event_id AND gives_to = OLD.user_id);  -- "their wishlist changed": not theirs any more
      INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, payload, send_after)
        SELECT g.user_id, 'santa_changed', 'event:' || OLD.event_id || ':' || lower(hex(randomblob(6))), '{{}}', 0
        FROM santa_people g WHERE g.event_id = OLD.event_id AND g.gives_to = OLD.user_id AND g.user_id != OLD.user_id
          AND (SELECT COUNT(*) FROM santa_people x WHERE x.event_id = OLD.event_id AND x.user_id != OLD.user_id) >= 3;
      INSERT OR IGNORE INTO bot_outbox (user_id, kind, ref, payload, send_after)
        SELECT p.user_id, CASE (SELECT COUNT(*) FROM santa_people x WHERE x.event_id = OLD.event_id AND x.user_id != OLD.user_id)
          WHEN 2 THEN 'santa_two' ELSE 'santa_alone' END, 'event:' || OLD.event_id, '{{}}', 0
        FROM santa_people p WHERE p.event_id = OLD.event_id AND p.user_id != OLD.user_id
          AND (SELECT COUNT(*) FROM santa_people x WHERE x.event_id = OLD.event_id AND x.user_id != OLD.user_id) IN (1, 2)
        ORDER BY p.user_id;
    END;""" for name, op, when in (("upd", "UPDATE OF status, user_id", " AND (NEW.status != 'going' OR NEW.user_id != OLD.user_id)"), ("del", "DELETE", "")))),
    # the people of the app (logic/credits.py): whose idea, find or code shipped, one line each in our words.
    # tg_id: no account needed; NULL once the account is deleted (the line stays, nameless). credit_consents: the
    # feature's own consent, every answer a row (who, when, yes or no, to which text), the latest counts
    (185, """CREATE TABLE IF NOT EXISTS credits (  -- IF NOT EXISTS: tests rewind user_version
      id INTEGER PRIMARY KEY,
      tg_id INTEGER,
      kind TEXT NOT NULL CHECK (kind IN ('idea', 'find', 'code')),
      ru TEXT NOT NULL,
      kk TEXT NOT NULL,
      en TEXT NOT NULL,
      shipped_on TEXT,  -- YYYY-MM-DD; NULL: suggested, not listed
      created_at INTEGER NOT NULL) STRICT;
    CREATE INDEX IF NOT EXISTS credits_tg ON credits (tg_id);
    CREATE TABLE IF NOT EXISTS credit_consents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,  -- never reused: a yes names the answer it follows (credits.answer's rev)
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      show INTEGER NOT NULL CHECK (show IN (0, 1)),  -- 0: a no, a withdrawal, or a grant ended by an account move
      version TEXT NOT NULL,  -- the consent text it answered
      at INTEGER NOT NULL) STRICT;
    CREATE INDEX IF NOT EXISTS credit_consents_user ON credit_consents (user_id, id);"""),
    # Give unedited channel drafts a cover by sharing the source image on disk.
    # Keep a separate event_cover row so the source post and draft retain their own file references.
    (186, """INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at, color)
    SELECT f.sha256, 'event_cover', f.mime, f.bytes, f.width, f.height, f.path, NULL, CAST(strftime('%s', 'now') AS INTEGER), f.color
    FROM files f WHERE f.id IN (SELECT p.photo_file_id FROM auto_events a
        JOIN events e ON e.id = a.event_id AND e.status = 'draft' AND e.updated_at <= e.created_at + 1 AND e.hidden_at IS NULL AND e.cover_file_id IS NULL
        JOIN posts p ON p.id = a.post_id AND p.hidden_at IS NULL)
      AND NOT EXISTS (SELECT 1 FROM files x WHERE x.path = f.path AND x.kind = 'event_cover' AND x.owner_id IS NULL);
    UPDATE events SET (cover_file_id, cover_focus) = (SELECT x.id, CASE WHEN x.height > x.width THEN '0.500,0.200' END
        FROM auto_events a JOIN posts p ON p.id = a.post_id AND p.hidden_at IS NULL JOIN files f ON f.id = p.photo_file_id
        JOIN files x ON x.path = f.path AND x.kind = 'event_cover' AND x.owner_id IS NULL WHERE a.event_id = events.id ORDER BY x.id LIMIT 1)
    WHERE status = 'draft' AND updated_at <= created_at + 1 AND hidden_at IS NULL AND cover_file_id IS NULL
      AND id IN (SELECT a.event_id FROM auto_events a JOIN posts p ON p.id = a.post_id AND p.hidden_at IS NULL WHERE p.photo_file_id IS NOT NULL);"""),
    # NULL reviewed_by also follows deletion of a human reviewer. Keep app provenance independently, without backfill.
    (187, """CREATE TABLE IF NOT EXISTS receipt_auto_checks (  -- IF NOT EXISTS: tests rewind user_version
      receipt_id INTEGER PRIMARY KEY REFERENCES receipts(id) ON DELETE CASCADE
    ) STRICT;"""),
    # an online event: NULL not online; '' online, no link yet; else its meeting link (core.online_url)
    (188, "ALTER TABLE events ADD COLUMN online TEXT;"),
    # the assistant's own yes to Google answering first (assistant.GOOGLE_YES, as team_consents): no row, never
    # Google; a withdrawal deletes the row
    (189, """CREATE TABLE IF NOT EXISTS kri_consents (  -- IF NOT EXISTS: tests rewind user_version
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      version TEXT NOT NULL,
      at INTEGER NOT NULL) STRICT;"""),
    # the yes goes with the student row, whatever removes it (deleting the account, the operator's
    # unlink, a staff row taken back): a later sign-in never finds an old yes waiting
    (190, """CREATE TRIGGER IF NOT EXISTS kri_consents_student_gone AFTER DELETE ON students BEGIN
      DELETE FROM kri_consents WHERE user_id = OLD.user_id;
    END;"""),
    # a credit by a GitHub login (credits.py): a pull request's author, the line never tied to an account
    # (tg_id NULL); the login is public already, so the line is shown under it
    (191, "ALTER TABLE credits ADD COLUMN gh TEXT;"),
    # users by lower(tg_username): account.support() on every /api/me and the @handle lookups (oversight, profiles, vol)
    # take an index instead of a scan; not partial: SQLite can't prove lower(x) = ? implies x IS NOT NULL
    (192, """CREATE INDEX IF NOT EXISTS users_handle ON users (lower(tg_username));"""),
    # (issue #44) scans EXPLAIN QUERY PLAN found on the main screens: my round applications on a club's page
    # (round_apps by user), a photo's event row in the gallery and the moderators' report count (event_photos by file:
    # SQLite built an automatic index per query), a photo's reports in the gallery (reports by target), Studio's role
    # list counting members per role (org_members by role)
    (193, """CREATE INDEX IF NOT EXISTS round_apps_by_user ON round_apps (user_id);
    CREATE INDEX IF NOT EXISTS event_photos_by_file ON event_photos (file_id);
    CREATE INDEX IF NOT EXISTS reports_by_target ON reports (target, target_id);
    CREATE INDEX IF NOT EXISTS members_by_role ON org_members (role_id);"""),
    (194, "ALTER TABLE users ADD COLUMN tg_photo_at INTEGER;"),
    # 195 is reserved on another branch. Merge it before deploying 196.
    (195, """CREATE TABLE IF NOT EXISTS ev_groups (  -- IDs are never reused after a draw.
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      advance INTEGER NOT NULL DEFAULT 2 CHECK (advance >= 0),
      position INTEGER NOT NULL,
      UNIQUE (event_id, position)) STRICT;
    CREATE TABLE IF NOT EXISTS ev_group_teams (
      group_id INTEGER NOT NULL REFERENCES ev_groups(id) ON DELETE CASCADE,
      team_id INTEGER NOT NULL UNIQUE REFERENCES event_teams(id) ON DELETE CASCADE,
      PRIMARY KEY (group_id, team_id)) STRICT;
    CREATE TABLE IF NOT EXISTS ev_matches (  -- A stale score entry must miss a replaced fixture.
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      group_id INTEGER NOT NULL REFERENCES ev_groups(id) ON DELETE CASCADE,
      home INTEGER NOT NULL REFERENCES event_teams(id) ON DELETE CASCADE,
      away INTEGER NOT NULL REFERENCES event_teams(id) ON DELETE CASCADE,
      home_score INTEGER CHECK (home_score >= 0),
      away_score INTEGER CHECK (away_score >= 0),
      played_at INTEGER,
      updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      CHECK (home < away),
      CHECK ((home_score IS NULL) = (away_score IS NULL)),
      UNIQUE (group_id, home, away)) STRICT;
    CREATE INDEX IF NOT EXISTS ev_matches_home ON ev_matches(home);
    CREATE INDEX IF NOT EXISTS ev_matches_away ON ev_matches(away);
    CREATE INDEX IF NOT EXISTS ev_matches_editor ON ev_matches(updated_by);"""),
    (196, """DROP TRIGGER IF EXISTS ev_matches_drop_group_team;
    ALTER TABLE ev_matches RENAME TO ev_matches_196;
    CREATE TABLE ev_matches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      group_id INTEGER REFERENCES ev_groups(id) ON DELETE CASCADE,
      stage TEXT NOT NULL DEFAULT 'group' CHECK (stage IN ('group', 'upper', 'lower', 'final')),
      round INTEGER,
      slot INTEGER,
      next_win INTEGER REFERENCES ev_matches(id),
      next_lose INTEGER REFERENCES ev_matches(id),
      home INTEGER REFERENCES event_teams(id) ON DELETE SET NULL,
      away INTEGER REFERENCES event_teams(id) ON DELETE SET NULL,
      home_score INTEGER CHECK (home_score >= 0),
      away_score INTEGER CHECK (away_score >= 0),
      played_at INTEGER,
      updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      CHECK ((home_score IS NULL) = (away_score IS NULL)),
      CHECK ((stage = 'group' AND group_id IS NOT NULL AND home IS NOT NULL AND away IS NOT NULL AND home < away
              AND round IS NULL AND slot IS NULL AND next_win IS NULL AND next_lose IS NULL)
          OR (stage != 'group' AND group_id IS NULL AND round IS NOT NULL AND round > 0 AND slot IS NOT NULL AND slot > 0
              AND (stage = 'upper' AND round = 1 OR home IS NULL AND away IS NULL)
              AND (home_score IS NULL OR home_score != away_score))),
      UNIQUE (group_id, home, away),
      UNIQUE (event_id, stage, round, slot)) STRICT;
    INSERT INTO ev_matches (id, event_id, group_id, home, away, home_score, away_score, played_at, updated_by)
      SELECT m.id, g.event_id, m.group_id, m.home, m.away, m.home_score, m.away_score, m.played_at, m.updated_by
      FROM ev_matches_196 m JOIN ev_groups g ON g.id = m.group_id;
    -- Keep IDs retired by a previous draw, even when the old match table is empty.
    INSERT INTO sqlite_sequence (name, seq) SELECT 'ev_matches', seq FROM sqlite_sequence WHERE name = 'ev_matches_196'
      AND NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'ev_matches');
    UPDATE sqlite_sequence SET seq = MAX(seq, COALESCE((SELECT seq FROM sqlite_sequence WHERE name = 'ev_matches_196'), 0))
      WHERE name = 'ev_matches';
    DROP TABLE ev_matches_196;
    CREATE INDEX ev_matches_home ON ev_matches(home);
    CREATE INDEX ev_matches_away ON ev_matches(away);
    CREATE INDEX ev_matches_editor ON ev_matches(updated_by);
    CREATE INDEX ev_matches_next_win ON ev_matches(next_win);
    CREATE INDEX ev_matches_next_lose ON ev_matches(next_lose);
    -- Group fixtures are dropped with either team. Bracket slots and results keep their place.
    CREATE TRIGGER ev_matches_drop_group_team BEFORE DELETE ON event_teams BEGIN
      DELETE FROM ev_matches WHERE stage = 'group' AND home = OLD.id;
      DELETE FROM ev_matches WHERE stage = 'group' AND away = OLD.id;
    END;"""),
    (197, """ALTER TABLE events ADD COLUMN guest_list INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE events ADD COLUMN age_check INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE event_guests (
      event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
      student_id TEXT NOT NULL,
      adult INTEGER CHECK (adult IN (0, 1)),
      surname_hash BLOB,
      PRIMARY KEY (event_id, student_id)
    ) STRICT;
    CREATE INDEX event_guests_by_student ON event_guests (student_id);
    CREATE TABLE reg_age (
      registration_id INTEGER PRIMARY KEY REFERENCES registrations(id) ON DELETE CASCADE,
      adult INTEGER NOT NULL CHECK (adult IN (0, 1)),
      set_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      set_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS outbox_u18 ON bot_outbox (ref) WHERE kind = 'u18_leave';"""),
    (198, "ALTER TABLE events ADD COLUMN silent_publish INTEGER NOT NULL DEFAULT 0;"),
    # Earlier pending officer claims provisionally granted membership. Keep the claim for a decision.
    (199, """DELETE FROM org_members AS m WHERE role = 'member' AND EXISTS (
      SELECT 1 FROM roster_pending r JOIN meta k ON k.key = 'rclaim:' || r.id
      WHERE r.org_id = m.org_id AND r.claimed_by = m.user_id AND k.value = CAST(m.user_id AS TEXT))
      AND (SELECT json_extract(data, '$.by') FROM audit_log WHERE target = 'user:' || m.user_id
        AND action = 'role_change' AND json_extract(data, '$.org') = m.org_id ORDER BY id DESC LIMIT 1) = 'roster';
    DELETE FROM meta WHERE key LIKE 'rclaim:%';"""),
    (200, """ALTER TABLE org_invites ADD COLUMN consumed INTEGER NOT NULL DEFAULT 0;
    UPDATE org_invites SET consumed = 1 WHERE used_by IS NOT NULL AND multi = 0;
    -- A legacy erasure could clear the only record of redemption. Retire ambiguous live links once.
    UPDATE org_invites SET revoked_at = unixepoch() WHERE multi = 0 AND consumed = 0 AND revoked_at IS NULL
      AND expires_at > unixepoch() AND created_at <= (SELECT MAX(at) FROM audit_log WHERE action = 'delete_my_data');"""),
    (201, """UPDATE receipts SET flags = 'ocr_unavailable' WHERE flags IN ('', 'partial')
        AND amount IS NULL AND receipt_no IS NULL AND reviewed_at IS NULL AND status = 'accepted';"""),
    (202, """CREATE TABLE IF NOT EXISTS appeal_ai_consents (
      user_id INTEGER PRIMARY KEY REFERENCES students(user_id) ON DELETE CASCADE,
      version TEXT NOT NULL, at INTEGER NOT NULL) STRICT;"""),
    (203, """ALTER TABLE registrations ADD COLUMN phone_shared INTEGER NOT NULL DEFAULT 0;
    CREATE TRIGGER signup_phone_changed AFTER UPDATE OF phone ON students WHEN old.phone IS NOT new.phone BEGIN
        UPDATE registrations SET phone_shared = 0 WHERE user_id = old.user_id AND phone_shared = 1;
    END;
    CREATE TRIGGER signup_phone_unlinked AFTER DELETE ON students BEGIN
        UPDATE registrations SET phone_shared = 0 WHERE user_id = old.user_id AND phone_shared = 1;
    END;
    CREATE TABLE retired_tickets (
        ticket_code TEXT PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE
    ) STRICT;
    CREATE INDEX retired_tickets_event ON retired_tickets(event_id);
    CREATE TABLE door_misses (
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        misses INTEGER NOT NULL,
        last_at INTEGER NOT NULL,
        PRIMARY KEY (event_id, user_id)
    ) STRICT;
    ALTER TABLE qr_expected ADD COLUMN door_key TEXT;
    UPDATE qr_expected SET door_key = lower(hex(randomblob(16)));
    CREATE UNIQUE INDEX qr_expected_door_key ON qr_expected(door_key);
    CREATE TRIGGER qr_expected_key AFTER INSERT ON qr_expected WHEN new.door_key IS NULL BEGIN
        UPDATE qr_expected SET door_key = lower(hex(randomblob(16))) WHERE rowid = new.rowid;
    END;
    UPDATE qr_hand_marks AS h SET who = 'x' || (SELECT x.door_key FROM qr_expected x
        WHERE x.session_id = h.session_id AND 'x' || x.email = h.who)
        WHERE EXISTS (SELECT 1 FROM qr_expected x WHERE x.session_id = h.session_id AND 'x' || x.email = h.who);
    DROP TRIGGER qr_hand_expected_gone;
    CREATE TRIGGER qr_hand_expected_gone AFTER DELETE ON qr_expected BEGIN
        DELETE FROM qr_hand_marks WHERE session_id = old.session_id AND who = 'x' || old.door_key;
    END;"""),
    (204, """-- Release username-only legacy links without a corroborated name. A later manual confirmation wins.
    CREATE TEMP TABLE vol_unconfirmed (vol_id INTEGER, user_id INTEGER, PRIMARY KEY (vol_id, user_id));
    INSERT INTO vol_unconfirmed
    SELECT t.vol_id, t.user_id FROM vol_ties t JOIN vol_people p ON p.id = t.vol_id
    LEFT JOIN students s ON s.user_id = t.user_id
    WHERE NOT expected_name(p.name, s.ms_oid, s.ms_profile, s.manual, s.first_name, s.last_name) AND (
        SELECT json_extract(a.data, '$.auto') FROM audit_log a
        WHERE a.action = 'vol_link' AND a.target = 'user:' || t.user_id AND json_extract(a.data, '$.vol') = t.vol_id
        ORDER BY a.id DESC LIMIT 1
    ) = 'tg';
    DELETE FROM vol_ties WHERE (vol_id, user_id) IN (SELECT vol_id, user_id FROM vol_unconfirmed)
        OR EXISTS (SELECT 1 FROM vol_people p WHERE p.id = vol_ties.vol_id AND p.user_id IS NOT NULL AND p.user_id != vol_ties.user_id);
    UPDATE vol_people SET user_id = NULL WHERE (id, user_id) IN (SELECT vol_id, user_id FROM vol_unconfirmed);
    DROP TABLE vol_unconfirmed;"""),
    (205, """CREATE TABLE fchan_hearts (
      post_id INTEGER NOT NULL REFERENCES fchan_posts(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      PRIMARY KEY (post_id, user_id)
    ) STRICT;
    CREATE INDEX fchan_hearts_by_user ON fchan_hearts(user_id);
    ALTER TABLE users ADD COLUMN forum_seen_msg INTEGER NOT NULL DEFAULT 0;"""),
    (206, """ALTER TABLE users ADD COLUMN n_forum_comments INTEGER NOT NULL DEFAULT 1;
    -- Carry pending anonymous-reply alerts and the last three hours of deliveries into the per-post cooldown.
    INSERT INTO bot_outbox (user_id, kind, ref, payload, send_after, sent_at)
      SELECT p.user_id, 'fch_comments', 'fc:' || p.id, '{"answer":true}', MAX(b.send_after),
        MAX(CASE WHEN b.sent_at IS NULL AND b.send_after > unixepoch() THEN unixepoch() ELSE b.sent_at END)
      FROM bot_outbox b JOIN fchan_replies r ON r.id = CAST(substr(b.ref, 4) AS INTEGER)
      JOIN fchan_posts p ON p.id = r.post_id AND p.user_id = b.user_id
      WHERE b.kind = 'fch_reply_answer' AND b.error IS NULL AND p.status = 'live'
        AND (b.sent_at IS NULL OR b.sent_at > unixepoch() - 10800)
      GROUP BY p.id;
    DELETE FROM bot_outbox WHERE kind = 'fch_reply_answer';"""),
    (207, """CREATE INDEX IF NOT EXISTS qr_running ON qr_sessions(id) WHERE started_at IS NOT NULL AND ended_at IS NULL;
    CREATE INDEX IF NOT EXISTS registrations_wait_order ON registrations(event_id, waitlisted_at, id) WHERE status = 'waitlist';
    CREATE INDEX IF NOT EXISTS reg_first_checkin ON registrations(event_id, checked_in_at) WHERE checked_in_at IS NOT NULL;
    CREATE INDEX IF NOT EXISTS saved_by_event ON saved_events(event_id);"""),
    # people let in at the door without the app (outsiders, ID checked by eye): a bare count, no one named
    (208, "ALTER TABLE events ADD COLUMN door_extra INTEGER NOT NULL DEFAULT 0 CHECK (door_extra >= 0);"),
    # a ticket buyer not in the app yet, let in by hand at the door (student ID + surname against the list): when
    (209, "ALTER TABLE event_guests ADD COLUMN came_at INTEGER;"),
    # the door's list by name (privacy policy: the organizer's expected list, its fields seen by the door team, gone
    # 24 h after the event with the row); people without a student ID get a row of their own ('x' + a number)
    (210, "ALTER TABLE event_guests ADD COLUMN name TEXT CHECK (name IS NULL OR length(name) <= 120);"),
    # the list's Telegram username: whoever opens the app with it gets the ticket at once, no KBTU sign-in needed
    (211, "ALTER TABLE event_guests ADD COLUMN username TEXT CHECK (username IS NULL OR length(username) <= 40);"),
    # the organizers' team names on the door's list (search a team, tick it at once): a list row's and an app guest's
    (212, """ALTER TABLE event_guests ADD COLUMN team TEXT CHECK (team IS NULL OR length(team) <= 80);
    ALTER TABLE registrations ADD COLUMN door_team TEXT CHECK (door_team IS NULL OR length(door_team) <= 80);"""),
    (213, """ALTER TABLE users ADD COLUMN n_broadcasts INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE users ADD COLUMN n_digests INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE users ADD COLUMN n_door INTEGER NOT NULL DEFAULT 1;
    UPDATE users SET n_door = n_remind;
    ALTER TABLE users ADD COLUMN notification_undo TEXT NOT NULL DEFAULT '{}';
    CREATE TABLE notification_days (
      day INTEGER NOT NULL,
      category TEXT NOT NULL,
      sent INTEGER NOT NULL DEFAULT 0,
      useful INTEGER NOT NULL DEFAULT 0,
      turned_off INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (day, category)
    ) STRICT;"""),
    (214, """ALTER TABLE registrations ADD COLUMN rating_dismissed INTEGER NOT NULL DEFAULT 0 CHECK (rating_dismissed IN (0, 1));
    ALTER TABLE event_ratings ADD COLUMN public_after INTEGER;
    -- A legacy vote qualifies only when the event has stayed public and unchanged since the vote.
    UPDATE event_ratings AS r SET public_after = (
        SELECT COALESCE(e.ends_at, e.starts_at + 10800) + 604800 FROM events e WHERE e.id = r.event_id
        AND e.status = 'published' AND e.hidden_at IS NULL AND e.visibility = 'public' AND e.school IS NULL
        AND e.updated_at < r.created_at AND COALESCE(e.ends_at, e.starts_at + 10800) <= r.created_at
    );"""),
    (215, """ALTER TABLE club_report_marks ADD COLUMN comment TEXT NOT NULL DEFAULT '' CHECK (length(comment) <= 300);
    ALTER TABLE club_report_marks ADD COLUMN comment_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    ALTER TABLE club_report_marks ADD COLUMN comment_at INTEGER;
    ALTER TABLE club_report_marks ADD COLUMN comment_edited_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
    ALTER TABLE club_report_marks ADD COLUMN comment_edited_at INTEGER;"""),
    (216, """CREATE TABLE IF NOT EXISTS web_sessions (
      digest BLOB PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at INTEGER NOT NULL,
      last_used_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS web_sessions_user ON web_sessions(user_id);
    CREATE INDEX IF NOT EXISTS web_sessions_last_used ON web_sessions(last_used_at);
    CREATE TABLE IF NOT EXISTS web_login_used (
      digest BLOB PRIMARY KEY,
      expires_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS web_login_used_expires ON web_login_used(expires_at);
    CREATE TRIGGER IF NOT EXISTS web_sessions_revoke AFTER UPDATE OF banned_at, tg_id ON users
      WHEN new.banned_at IS NOT NULL OR old.tg_id != new.tg_id BEGIN
        DELETE FROM web_sessions WHERE user_id = old.id;
      END;"""),
    (217, """CREATE TABLE fchan_feed_pages (
      token TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      sort TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      post_ids BLOB NOT NULL
    ) STRICT;
    CREATE INDEX fchan_feed_pages_by_user ON fchan_feed_pages(user_id, sort, expires_at DESC);
    CREATE INDEX fchan_feed_pages_expiry ON fchan_feed_pages(expires_at);"""),
    # a photo's report gets "not from this event" (a meme, a screenshot): the CHECK can't be altered, so the table is
    # rebuilt (nothing references reports)
    (218, """CREATE TABLE reports7 (
        id INTEGER PRIMARY KEY,
        reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        target TEXT NOT NULL CHECK (target IN ('post', 'comment', 'event', 'user', 'org', 'photo', 'ask', 'thread', 'reply', 'fpost')),
        target_id INTEGER NOT NULL,
        reason TEXT NOT NULL CHECK (reason IN ('spam', 'insult', 'danger', 'other', 'rules', 'offtopic', 'me')),
        note TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
        created_at INTEGER NOT NULL,
        resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        resolved_at INTEGER
    ) STRICT;
    INSERT INTO reports7 SELECT id, reporter_id, target, target_id, reason, note, status, created_at, resolved_by, resolved_at FROM reports;
    DROP TABLE reports;
    ALTER TABLE reports7 RENAME TO reports;
    CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id) WHERE status = 'open';
    CREATE INDEX reports_by_target ON reports (target, target_id);"""),
    # public forms (logic/forms.py): anonymous answers, so no user, IP or cookie column on purpose
    (219, """CREATE TABLE IF NOT EXISTS forms (
      id INTEGER PRIMARY KEY,
      slug TEXT NOT NULL UNIQUE,
      spec TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      closed_at INTEGER
    ) STRICT;
    CREATE TABLE IF NOT EXISTS form_answers (
      id INTEGER PRIMARY KEY,
      form_id INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
      answers TEXT NOT NULL,
      created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS form_answers_by_form ON form_answers(form_id, created_at);"""),
    # /all in a club's group kept to its Telegram admins (Studio's switch); a group not here: its club roles call too
    (220, "CREATE TABLE IF NOT EXISTS chat_call_admins (chat_id INTEGER PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE) STRICT;"),
    # Secret Santa's chat (logic/santa.py): one thread per pair, kept by both its people; text NULL: that side reported
    # the thread (closed; done_at: staff handled it). santa_chats.until: the chat's end, fixed at the draw (the gifts day + 3
    # days: an edit of the event never revives it); 0 once anyone left the ring: the chat is retired for everyone alike
    # and its words go (whose thread vanished would name a Santa), a reported thread stays for the staff.
    # santa_sends: the day's count of my messages, apart from them so a deleted thread refunds nothing
    (221, """CREATE TABLE IF NOT EXISTS santa_msgs (
      id INTEGER PRIMARY KEY,
      event_id INTEGER NOT NULL REFERENCES santa_events(event_id) ON DELETE CASCADE,
      giver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      to_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      from_giver INTEGER NOT NULL CHECK (from_giver IN (0, 1)),
      text TEXT CHECK (length(text) BETWEEN 1 AND 500),
      created_at INTEGER NOT NULL,
      done_at INTEGER) STRICT;
    CREATE INDEX IF NOT EXISTS santa_msgs_thread ON santa_msgs (event_id, giver_id, to_id);
    CREATE INDEX IF NOT EXISTS santa_msgs_to ON santa_msgs (to_id);
    CREATE INDEX IF NOT EXISTS santa_msgs_giver ON santa_msgs (giver_id);
    CREATE TABLE IF NOT EXISTS santa_sends (
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      at INTEGER NOT NULL) STRICT;
    CREATE INDEX IF NOT EXISTS santa_sends_by_user ON santa_sends (user_id, at);
    CREATE TABLE IF NOT EXISTS santa_chats (  -- its own table, not a column: tests rewind user_version
      event_id INTEGER PRIMARY KEY REFERENCES santa_events(event_id) ON DELETE CASCADE,
      until INTEGER NOT NULL) STRICT;
    INSERT OR IGNORE INTO santa_chats (event_id, until) SELECT s.event_id, e.starts_at + 259200 FROM santa_events s
      JOIN events e ON e.id = s.event_id WHERE s.drawn_at IS NOT NULL;
    CREATE TRIGGER IF NOT EXISTS santa_msgs_gone AFTER DELETE ON santa_people BEGIN
      UPDATE santa_chats SET until = 0 WHERE event_id = OLD.event_id;
      DELETE FROM santa_msgs WHERE event_id = OLD.event_id AND NOT EXISTS (SELECT 1 FROM santa_msgs r
        WHERE r.event_id = santa_msgs.event_id AND r.giver_id = santa_msgs.giver_id AND r.to_id = santa_msgs.to_id AND r.text IS NULL);
    END;"""),
    (222, "ALTER TABLE posts ADD COLUMN tg_fmt TEXT;"),
    # logic/helpus.py: an anonymous line to the creator (no user column and only the day, on purpose) and a signed offer to help
    (223, """CREATE TABLE IF NOT EXISTS anon_feedback (
      id INTEGER PRIMARY KEY,
      body TEXT NOT NULL CHECK (length(body) <= 1000),
      day INTEGER NOT NULL
    ) STRICT;
    CREATE TABLE IF NOT EXISTS helper_offers (
      id INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id),
      kinds TEXT NOT NULL,
      note TEXT CHECK (note IS NULL OR length(note) <= 500),
      consent TEXT NOT NULL,
      created_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS helper_offers_by_user ON helper_offers(user_id, created_at);
    CREATE INDEX IF NOT EXISTS anon_feedback_by_day ON anon_feedback(day);"""),
    # where a Gallery photo was taken, as one of four words the phone itself picked from the photo's EXIF (gallery.PLACES);
    # the coordinates never arrive
    (224, "ALTER TABLE gallery_photos ADD COLUMN place TEXT CHECK (place IN ('main', 'b2', 'dorm', 'away'));"),
    (225, """CREATE TABLE IF NOT EXISTS gallery_consents (
        user_id INTEGER PRIMARY KEY NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        version TEXT NOT NULL,
        allowed INTEGER NOT NULL CHECK (allowed IN (0, 1)),
        at INTEGER NOT NULL
    ) STRICT;"""),
    # a broadcast's Interesting / Not interesting (bot._tapped): one vote per person per broadcast, to learn what to send
    (226, """CREATE TABLE IF NOT EXISTS broadcast_votes (
      name TEXT NOT NULL,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      vote INTEGER NOT NULL CHECK (vote IN (0, 1)),
      at INTEGER NOT NULL,
      PRIMARY KEY (name, user_id)
    ) STRICT;"""),
    # Forum research: native student surveys and signed proposals; approval never creates a form.
    (228, """CREATE TABLE IF NOT EXISTS research_forms (
      form_id INTEGER PRIMARY KEY REFERENCES forms(id) ON DELETE CASCADE,
      about TEXT NOT NULL CHECK (length(about) BETWEEN 1 AND 200)
    ) STRICT;
    INSERT OR IGNORE INTO research_forms (form_id, about)
      SELECT id, substr(COALESCE(NULLIF(trim(replace(json_extract(spec, '$.intro'), char(10), ' ')), ''),
        json_extract(spec, '$.title')), 1, 200) FROM forms WHERE slug = 'library';
    CREATE TABLE IF NOT EXISTS research_requests (
      id INTEGER PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
      goal TEXT NOT NULL CHECK (length(goal) BETWEEN 1 AND 1200),
      questions TEXT NOT NULL CHECK (length(questions) BETWEEN 1 AND 4000),
      organizer TEXT NOT NULL CHECK (length(organizer) BETWEEN 1 AND 200),
      consent TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      approved_at INTEGER
    ) STRICT;
    CREATE INDEX IF NOT EXISTS research_requests_by_user ON research_requests(user_id, created_at);
    CREATE TABLE IF NOT EXISTS research_answers (
      id TEXT PRIMARY KEY NOT NULL,
      form_id INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      answers TEXT NOT NULL,
      consent TEXT NOT NULL,
      day INTEGER CHECK ((day IS NULL) = (user_id IS NULL))
    ) STRICT, WITHOUT ROWID;
    CREATE INDEX IF NOT EXISTS research_answers_by_form ON research_answers(form_id);
    CREATE INDEX IF NOT EXISTS research_answers_by_user ON research_answers(user_id);
    -- No timestamp, answer key or insertion sequence: participation cannot identify an anonymous answer.
    CREATE TABLE IF NOT EXISTS research_participants (
      form_id INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      PRIMARY KEY (form_id, user_id)
    ) STRICT, WITHOUT ROWID;
    CREATE INDEX IF NOT EXISTS research_participants_by_user ON research_participants(user_id);"""),
]
