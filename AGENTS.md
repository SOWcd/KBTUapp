# AGENTS.md

How to work on KBTU App, for any coding agent (Claude Code, Codex, Cursor, ...) and for people. Read this first.
What the app is and how to run it: [README.md](README.md). How to contribute: [CONTRIBUTING.md](CONTRIBUTING.md).

## The goals (the owner's hard rules, in this order)

1. **Speed and convenience.** The app is incredibly fast and effortless: every tap answers in the same frame, nothing
   waits that could be ready, every flow takes the fewest taps.
2. **Beauty, never at speed's cost.** Visuals, motion and style are as beautiful, modern, aesthetic and professional
   as the best iOS apps. How it works inside doesn't matter; what the person sees and feels does. No visible seams,
   bands, jumps or mismatched colours ship.
3. **A simple repository.** The code stays clear, minimal and efficient, so any agent or person understands it fast:
   no bloat, no speculative layers, delete before adding.

Both 1 and 2 matter; when they truly conflict, faster and more convenient wins. We never stand still: the app is
improved screen by screen toward ideal (owner, Nov 23): design goes to the best model by contest (so far Fable), one
screen per PR, never slower than before, checked on a phone in both themes.

## The project in one screen

- A Telegram Mini App for KBTU students: events and tickets (free and paid by Kaspi receipt), clubs and their
  Studio, news, friends, awards, the class timetable, the campus map, QR check-in on a big screen (`/show`), the
  student forum. Unofficial; Russian, Kazakh and English.
- `web/`: Svelte 5 (runes) + Vite + TypeScript, a static build served by the server.
- `server/`: Python 3, FastAPI, SQLite (WAL). The API, the Telegram bot (`bot.py`) and the nightly jobs run in one
  process. Rules live in `server/kbtu/logic/` (one module per area) and a few big modules beside it (`casting.py`, `checkin.py`, `roster.py`, `admin.py`); `app.py` only routes.
- One Docker image (`Dockerfile`). **A push to `main` deploys production**: never push without the owner's yes.

## Where things are

| What | Where |
| --- | --- |
| API routes | `server/kbtu/app.py` |
| Rules by area | `server/kbtu/logic/*.py` (`core` shared helpers; `seats` sign-up and tickets; `organizing` Studio, the door; `fchannel` the forum channel's posts; `tgcomments` its comments; `forum` find-people; `account` me, settings, deleting an account; `moderation` reports; `daily` the weekly DMP memo and `stats_day` (the nightly retention sweep: a new cleanup goes there; the scheduler is `bot.py::_chores`); `clubs` clubs and join requests (`join_requests`; not `club_applications` = a new club, nor `casting` = recruitment rounds); `stats` anonymous usage counters; `credits` the people of the app, its own consent; `helpus` to the creator from the app: an anonymous line (no author kept, by design) and a signed offer to help) |
| Schema | read `server/kbtu/schema.current.sql` (generated: today's tables); change it only by appending to `MIGRATIONS` in `server/kbtu/migrations.py` (read that file with `tail`), then run `server/tools/schema_dump.py` |
| Bot texts | `server/kbtu/texts.py` (ru, kk, en, the same placeholders in each) |
| Privacy policy, terms | `server/kbtu/i18n/legal/*.html` (Russian binding) |
| QR check-in, `/show` | `server/kbtu/checkin.py`, `web/src/screens/Screen.svelte` |
| Web entry, tabs, sheets | `web/src/App.svelte`, `web/src/lib/state/ui.svelte.ts`, `web/src/lib/state/sheets.ts` |
| API contract | `web/src/lib/api/types.ts`, `index.ts` (the interface), `client.ts` |
| UI strings | `web/src/lib/i18n/{ru,kk,en}.ts` (ru is the source; kk and en are typed against it). ~70k tokens each: never read them whole; grep the key prefix and edit by anchor in all three |
| Shared UI | `web/src/ui/` (tokens.css, base.css, glass, Sheet, Button, ...) |
| Test helpers | `env`, `login`, `tma`, `set_clock` in `server/tests/test_core.py` (import them from there) |
| Android app (Play) | `android/` (a TWA from `twa-manifest.json`; README: release, demo login, Data safety), built only by `.github/workflows/android.yml` |
| Deep links | parsed in `web/src/App.svelte` (`deepLink`): `ev_<id>`, `cl_<id>`, ... |

## Run and check

```bash
cd web && npm ci && npm run build                     # the build fails if a bundle uses regex lookbehind (old iOS)
cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest pytest-xdist
.venv/bin/python tools/qa.py --port 8790              # a seeded server; prints a signed link per made-up person
```

Before every commit, all of these pass:

```bash
cd server && .venv/bin/python -m pytest -q -n auto tests   # ~5 min on 4 cores
cd web && npm run check && npm test                   # svelte-check 0 errors, 0 warnings; vitest
```

One file: `pytest -q tests/test_x.py -k name` (~1 min: the schema and migrations are built per process). `npm test`
includes a design ratchet (`web/src/lib/design.test.ts`): new raw hex/font/radius values fail it.

Checking a screen: open a link `qa.py` prints, at phone size (375 px, also 320), in both themes. A hidden browser
tab freezes animations and `requestAnimationFrame`: look with it visible.

## Rules

- **English everywhere outside UI strings**: code, comments, commits, docs. UI text only in `web/src/lib/i18n/`
  (all three languages at once) and the bot's in `texts.py`. A pre-commit hook refuses Cyrillic elsewhere; in tests
  write it as `\u` escapes. The hook is `.githooks/pre-commit`: turn it on once per clone with
  `git config core.hooksPath .githooks`; CI runs the same check on what a PR adds.
- **The database**: never edit `schema.sql`; append a migration (one transaction). A CHECK can't be altered in
  SQLite and a table rebuild with foreign keys on cascades deletes into its children: prefer a new table or column.
- **Personal data**: never in the repo, logs or screenshots. One policy by data categories, one consent
  version for everyone (`CONSENT` in `logic/account.py`), whatever the flags. A new category of personal data: the
  policy says so first (Codex writes it), and the feature asks its own consent inside itself (like `appeals.CONSENT`),
  never a suffix on the version.
  Deleting an account must cover every new table (`_DEL_GONE` in `logic/account.py`; a test checks the schema).
- **Limits**: a per-day cap counts the table's own rows in the last 86400 s inside `db.tx` and raises
  `ApiError("rate_limited", "<why>")` (e.g. `logic/mapflaws.py`).
- **Speed**: a tap answers in the same frame (optimistic UI); a page never waits for its data when it opens (the
  store loads it with the app, `lib/state/data.svelte.ts`); heavy screens are lazy chunks; lists read each fact
  once for all rows, never card by card.
- **The bot** sends templates with a button into the app, never a user's words. The few exceptions (forum channel posts and
  replies, `/all`, restored comments, share cards, group video replies) are listed in `server/kbtu/BOT_WORDS.md`: read
  it before touching bot.py, fchannel.py, tgcomments.py or tiktok.py.
- **Bot texts the owner sees first**: every bot message opens with an emoji (a test checks), is short (a few
  lines, emoji over words), and a new or changed one, above all a broadcast, goes to the owner as a preview
  (`admin broadcast ... @who`, or a screenshot) for his yes before anyone else gets it.
- **One interface for everyone**: the app looks and works exactly the same for every person: a student, a moderator,
  an admin, the creator. Staff get one extra thing, the Admin sheet; every staff and moderation control lives there
  and nowhere else (no "take down", "publish", "reveal" or role badges with actions in normal tabs). A club's own
  people managing their club in Studio is not staff. Destructive staff actions confirm first and can be undone.
- **One Back**: Telegram's BackButton is the only Back. No "‹ Back" links, arrows or close buttons of our own that
  duplicate it (a full-screen overlay's bottom x is the one exception: ui/CloseX.svelte).
- **Svelte**: runes only. `@keyframes` are scoped per component: define the ones you use. The official Svelte MCP (`.mcp.json`) has the docs and
  `svelte-autofixer`: run a new or changed component through it until it reports nothing.
- **Style**: match the code around you; short comments that say why. Deliberate shortcuts are marked
  `# ponytail:` / `// ponytail:` with their ceiling and the upgrade path.
- **Security reviews**: features that touch money, check-in, anonymity or personal data get an adversarial review
  (a second agent trying to break them) before they ship.

## Feature switches

Server env switches (`FORUM`, `BOARD`, `DOCS`, `REPORTS`, `TIKTOK`, `INSTAGRAM_COOKIES`, `FORUM_CHANNEL`, ...): README.md "Feature switches".
No switch changes the policy or the consent version.
