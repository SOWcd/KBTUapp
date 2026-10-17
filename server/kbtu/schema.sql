-- KBTU App schema: SPEC §5, the source of truth. Applied once to an empty database (PRAGMA user_version 0 → 1);
-- later changes go into kbtu/db.py as numbered migrations, and SPEC §5 is updated with them.

-- Telegram account; exists for guests too (created on the first API call).
CREATE TABLE users (
  id              INTEGER PRIMARY KEY,
  tg_id           INTEGER NOT NULL UNIQUE,
  tg_username     TEXT,
  tg_first_name   TEXT NOT NULL DEFAULT '',
  tg_last_name    TEXT NOT NULL DEFAULT '',
  avatar_file_id  INTEGER REFERENCES files(id),     -- my own photo, shown while avatar_tg = 0 (migration 16)
  tg_photo_url    TEXT,                             -- pilot: the public t.me/i/userpic link from initData (no token in it)
  lang            TEXT NOT NULL DEFAULT 'ru' CHECK (lang IN ('ru','kk','en')),
  theme           TEXT CHECK (theme IN ('light','dark')),   -- NULL = follow Telegram
  role            TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','moderator','admin')),
  is_founder      INTEGER NOT NULL DEFAULT 0,
  can_dm          INTEGER NOT NULL DEFAULT 0,       -- bot may write to them
  n_remind        INTEGER NOT NULL DEFAULT 1,       -- 2 h reminder
  n_new_events    INTEGER NOT NULL DEFAULT 1,       -- new events from subscriptions
  n_friends       INTEGER NOT NULL DEFAULT 1,       -- Monday friends digest
  show_going      INTEGER NOT NULL DEFAULT 1,       -- friends see where I go
  hide_first_year INTEGER NOT NULL DEFAULT 0,
  bio             TEXT NOT NULL DEFAULT '' CHECK (length(bio) <= 150),   -- "about me", public to students
  showcase        TEXT NOT NULL DEFAULT '',         -- up to 3 achievement codes, comma-separated
  banned_at       INTEGER,
  ban_reason      TEXT,
  created_at      INTEGER NOT NULL,
  seen_at         INTEGER NOT NULL
) STRICT;

-- KBTU-verified profile from the portal (1:1, absent for guests).
CREATE TABLE students (
  user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  student_id      TEXT NOT NULL UNIQUE,             -- e.g. 24B031234
  first_name      TEXT NOT NULL,
  last_name       TEXT NOT NULL,
  middle_name     TEXT,
  email           TEXT,
  phone           TEXT,
  course          INTEGER,
  degree          TEXT,                             -- bachelor / master / … as the portal says
  school          TEXT,
  program         TEXT,
  consent_version TEXT NOT NULL,
  consent_at      INTEGER NOT NULL,
  verified_at     INTEGER NOT NULL,
  synced_at       INTEGER NOT NULL
) STRICT;

CREATE TABLE schedule_classes (
  id      INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),   -- 1 = Monday
  begins  TEXT NOT NULL,                            -- 'HH:MM' Almaty
  ends    TEXT NOT NULL,
  subject TEXT NOT NULL,
  code    TEXT,
  kind    TEXT,                                     -- lecture / practice / lab
  room    TEXT,
  teacher TEXT
) STRICT;
CREATE INDEX schedule_by_user ON schedule_classes(user_id, weekday);

CREATE TABLE orgs (
  id               INTEGER PRIMARY KEY,
  slug             TEXT NOT NULL UNIQUE,            -- [a-z0-9]{2,24}, used in deep links
  kind             TEXT NOT NULL CHECK (kind IN ('club','school','council','office','app')),
  name             TEXT NOT NULL,
  short            TEXT NOT NULL,                   -- 1–2 letters
  description      TEXT NOT NULL DEFAULT '',
  emoji            TEXT NOT NULL,                   -- key in the 3D emoji set
  cover            INTEGER NOT NULL DEFAULT 0,      -- index in the cover palette
  logo_file_id     INTEGER REFERENCES files(id),
  link             TEXT,
  can_broadcast    INTEGER NOT NULL DEFAULT 0,      -- posts to every club member (DMP, KBTU App)
  can_oversee      INTEGER NOT NULL DEFAULT 0,      -- clubs registry (DMP)
  official         INTEGER NOT NULL DEFAULT 0,      -- registered with DMP: ✓ badge; others are "student initiative"
  recruiting_until INTEGER,                         -- "Recruiting until …"; NULL = not recruiting
  status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','hidden','archived')),
  created_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at       INTEGER NOT NULL
) STRICT;

CREATE TABLE org_members (
  org_id    INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role      TEXT NOT NULL CHECK (role IN ('member','head','vice','president')),
  joined_at INTEGER NOT NULL,
  PRIMARY KEY (org_id, user_id)
) STRICT;
CREATE UNIQUE INDEX one_president ON org_members(org_id) WHERE role = 'president';
CREATE INDEX members_by_user ON org_members(user_id);

CREATE TABLE org_invites (
  token      TEXT PRIMARY KEY,                      -- random, ≥ 96 bits
  org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK (role IN ('member','president')),
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER,                               -- president links: 7 days
  used_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,   -- president links are single-use
  revoked_at INTEGER
) STRICT;

CREATE TABLE join_requests (
  id         INTEGER PRIMARY KEY,
  org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected','withdrawn')),
  created_at INTEGER NOT NULL,
  decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  decided_at INTEGER
) STRICT;
CREATE UNIQUE INDEX one_pending_request ON join_requests(org_id, user_id) WHERE status = 'pending';

CREATE TABLE club_applications (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  short       TEXT NOT NULL,
  description TEXT NOT NULL,
  emoji       TEXT NOT NULL,
  cover       INTEGER NOT NULL,
  link        TEXT,
  why         TEXT NOT NULL CHECK (length(why) BETWEEN 1 AND 500),   -- "why this club, what in the first month": the creator's filter
  status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  reason      TEXT,
  org_id      INTEGER REFERENCES orgs(id) ON DELETE SET NULL,
  created_at  INTEGER NOT NULL,
  decided_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  decided_at  INTEGER
) STRICT;
CREATE UNIQUE INDEX one_pending_application ON club_applications(user_id) WHERE status = 'pending';

CREATE TABLE subscriptions (
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id     INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, org_id)
) STRICT;
CREATE INDEX subs_by_org ON subscriptions(org_id, created_at);

CREATE TABLE events (
  id            INTEGER PRIMARY KEY,
  org_id        INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','cancelled')),
  title         TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  starts_at     INTEGER,
  ends_at       INTEGER,
  place         TEXT NOT NULL DEFAULT '',
  place_url     TEXT,                               -- 2GIS link for off-campus places ("Route in 2GIS")
  cover_file_id INTEGER REFERENCES files(id),       -- photo or poster; NULL → emoji + colour
  emoji         TEXT,
  color         TEXT,                               -- '#RRGGBB'
  tint          TEXT,                               -- sheet tint, from photo or colour
  seats         INTEGER CHECK (seats > 0),          -- NULL = no limit
  first_year    INTEGER NOT NULL DEFAULT 0,         -- "1st year" tag
  visibility    TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public','members','leaders')),  -- members = team-only; leaders = DMP meeting
  leaders_from  TEXT CHECK (leaders_from IN ('president','vice','head')),  -- leaders meetings: lowest invited role
  comments_on   INTEGER NOT NULL DEFAULT 1,
  external_url  TEXT,                               -- registration elsewhere instead of "Going"
  price         INTEGER CHECK (price > 0),          -- tenge; NULL = free
  pay_to_name   TEXT,                               -- recipient as printed on the Kaspi receipt
  pay_phone     TEXT,
  badge_name    TEXT,                               -- memorial badge; NULL = none
  co_org_id     INTEGER REFERENCES orgs(id) ON DELETE SET NULL,  -- co-organizer: shown on both pages, its Member+ may scan
  created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  published_at  INTEGER,
  cancelled_at  INTEGER,
  hidden_at     INTEGER,                            -- hidden by a moderator
  CHECK (status = 'draft' OR starts_at IS NOT NULL),
  CHECK (status = 'draft' OR price IS NULL OR (pay_to_name IS NOT NULL AND pay_phone IS NOT NULL))
) STRICT;
CREATE INDEX events_upcoming ON events(status, starts_at);
CREATE INDEX events_by_org ON events(org_id, starts_at);

CREATE TABLE registrations (
  id            INTEGER PRIMARY KEY,
  event_id      INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status        TEXT NOT NULL CHECK (status IN ('hold','going','waitlist','cancelled')),
  cancel_reason TEXT CHECK (cancel_reason IN ('self','hold_expired','receipt_rejected','removed')),
  ticket_code   TEXT NOT NULL UNIQUE,
  hold_until    INTEGER,
  waitlisted_at INTEGER,                            -- queue order
  invited_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  checked_in_at INTEGER,
  checked_in_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  UNIQUE (event_id, user_id)
) STRICT;
CREATE INDEX regs_by_user ON registrations(user_id, status);
CREATE INDEX regs_by_event ON registrations(event_id, status);
-- taken seats = COUNT(*) WHERE status IN ('hold','going'); count + insert in one BEGIN IMMEDIATE transaction

CREATE TABLE receipts (
  id              INTEGER PRIMARY KEY,
  registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
  file_id         INTEGER NOT NULL REFERENCES files(id),
  via             TEXT NOT NULL CHECK (via IN ('app','bot')),
  amount          INTEGER,                          -- as read from the receipt; NULL = unreadable
  receipt_no      TEXT,
  sender_name     TEXT,
  recipient_name  TEXT,
  paid_at         INTEGER,
  flags           TEXT NOT NULL DEFAULT '',         -- duplicate,unreadable,amount_short,amount_over,recipient_mismatch,too_early
  status          TEXT NOT NULL DEFAULT 'accepted' CHECK (status IN ('accepted','rejected')),
  reviewed_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  reviewed_at     INTEGER,                          -- NULL = organizer hasn't looked yet
  created_at      INTEGER NOT NULL
) STRICT;
CREATE INDEX receipts_by_reg ON receipts(registration_id);
CREATE INDEX receipts_by_no ON receipts(receipt_no);

CREATE TABLE saved_events (
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, event_id)
) STRICT;

CREATE TABLE event_photos (
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  file_id  INTEGER NOT NULL REFERENCES files(id),
  sort     INTEGER NOT NULL,
  added_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  PRIMARY KEY (event_id, file_id)
) STRICT;

CREATE TABLE posts (
  id             INTEGER PRIMARY KEY,
  org_id         INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  author_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
  audience       TEXT NOT NULL DEFAULT 'public' CHECK (audience IN ('public','clubs')),
  title          TEXT NOT NULL,
  body           TEXT NOT NULL DEFAULT '',
  tag            TEXT,                              -- short label: "Important", "Recruiting"
  photo_file_id  INTEGER REFERENCES files(id),
  pinned         INTEGER NOT NULL DEFAULT 0,        -- top of the org's news
  featured_until INTEGER,                           -- pinned card in List for everyone
  comments_on    INTEGER NOT NULL DEFAULT 1,
  created_at     INTEGER NOT NULL,
  edited_at      INTEGER,
  hidden_at      INTEGER
) STRICT;
CREATE INDEX posts_by_org ON posts(org_id, created_at);
CREATE INDEX posts_recent ON posts(audience, created_at);

CREATE TABLE post_reactions (
  post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind    TEXT NOT NULL CHECK (kind IN ('fire','heart')),
  PRIMARY KEY (post_id, user_id, kind)
) STRICT;

CREATE TABLE post_reads (                            -- views count + unread marks on broadcasts
  post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  read_at INTEGER NOT NULL,
  PRIMARY KEY (post_id, user_id)
) STRICT;

CREATE TABLE comments (                            -- under a post or under an event
  id         INTEGER PRIMARY KEY,
  post_id    INTEGER REFERENCES posts(id) ON DELETE CASCADE,
  event_id   INTEGER REFERENCES events(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  as_org     INTEGER NOT NULL DEFAULT 0,            -- written as the club (Head+)
  body       TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 500),
  created_at INTEGER NOT NULL,
  deleted_at INTEGER,
  deleted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  CHECK ((post_id IS NULL) <> (event_id IS NULL))
) STRICT;
CREATE INDEX comments_by_post ON comments(post_id, created_at);
CREATE INDEX comments_by_event ON comments(event_id, created_at);

CREATE TABLE reports (
  id          INTEGER PRIMARY KEY,
  reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  target      TEXT NOT NULL CHECK (target IN ('post','comment','event','user','org')),
  target_id   INTEGER NOT NULL,
  reason      TEXT NOT NULL CHECK (reason IN ('spam','insult','danger','other')),
  note        TEXT,
  status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','actioned','dismissed')),
  created_at  INTEGER NOT NULL,
  resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  resolved_at INTEGER
) STRICT;
CREATE UNIQUE INDEX one_report ON reports(reporter_id, target, target_id);

CREATE TABLE friendships (
  a          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  b          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (a, b),
  CHECK (a < b)
) STRICT;
CREATE INDEX friendships_b ON friendships(b);

CREATE TABLE friend_links (                          -- one-time invite link / QR
  token      TEXT PRIMARY KEY,                      -- random, ≥ 96 bits
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,                      -- 7 days
  used_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  used_at    INTEGER
) STRICT;

CREATE TABLE friend_requests (
  from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','declined')),
  created_at INTEGER NOT NULL,
  decided_at INTEGER,
  PRIMARY KEY (from_id, to_id)                      -- one row per direction; re-ask after 30 days updates it
) STRICT;
CREATE INDEX friend_requests_to ON friend_requests(to_id, status);

CREATE TABLE friend_invites (                        -- "Bring a friend"
  from_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  to_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  answer     TEXT CHECK (answer IN ('going','declined')),
  created_at INTEGER NOT NULL,
  PRIMARY KEY (from_id, to_id, event_id)
) STRICT;

CREATE TABLE achievement_grants (                    -- manual achievements; one row = +1
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code       TEXT NOT NULL,
  granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  note       TEXT,
  created_at INTEGER NOT NULL
) STRICT;
CREATE INDEX grants_by_user ON achievement_grants(user_id, code);

CREATE TABLE achievement_levels (                    -- last notified level, so "new achievement" is sent once
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code       TEXT NOT NULL,
  level      INTEGER NOT NULL,
  reached_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, code)
) STRICT;

CREATE TABLE chats (
  id         INTEGER PRIMARY KEY,
  title      TEXT NOT NULL,
  kind       TEXT NOT NULL CHECK (kind IN ('channel','group')),
  url        TEXT NOT NULL,                         -- t.me link
  tg_chat_id INTEGER,                               -- set when the bot is inside
  members    INTEGER,
  school     TEXT,                                  -- NULL = everyone
  course     INTEGER,                               -- NULL = every course
  sort       INTEGER NOT NULL DEFAULT 0,
  added_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL
) STRICT;

CREATE TABLE chat_opens (
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  chat_id   INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  opened_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, chat_id)
) STRICT;

CREATE TABLE files (
  id         INTEGER PRIMARY KEY,
  sha256     TEXT NOT NULL,
  kind       TEXT NOT NULL CHECK (kind IN ('avatar','event_cover','event_photo','post_photo','org_logo','receipt')),
  mime       TEXT NOT NULL,
  bytes      INTEGER NOT NULL,
  width      INTEGER,
  height     INTEGER,
  path       TEXT NOT NULL,                         -- receipts live in a private directory
  owner_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL
) STRICT;
CREATE INDEX files_by_hash ON files(sha256);

CREATE TABLE bot_outbox (
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL,
  ref        TEXT NOT NULL DEFAULT '',              -- dedupe part, e.g. 'event:12:v3'
  payload    TEXT NOT NULL DEFAULT '{}',
  send_after INTEGER NOT NULL,
  sent_at    INTEGER,
  error      TEXT,
  UNIQUE (user_id, kind, ref)
) STRICT;
CREATE INDEX outbox_due ON bot_outbox(sent_at, send_after);

CREATE TABLE audit_log (
  id       INTEGER PRIMARY KEY,
  actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  action   TEXT NOT NULL,                           -- role_change, presidency_transfer, receipt_reject, hide, ban, grant, pd_lookup, …
  target   TEXT NOT NULL,                           -- 'event:12', 'user:5'
  data     TEXT NOT NULL DEFAULT '{}',
  at       INTEGER NOT NULL
) STRICT;
