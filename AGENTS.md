# AGENTS.md

How to work on KBTU App, for any coding agent (Claude Code, Codex, Cursor, ...) and for people. Read this first.
What the app is and how to run it: [README.md](README.md). How to contribute: [CONTRIBUTING.md](CONTRIBUTING.md).

## The project in one screen

- A Telegram Mini App for KBTU students: events and tickets (free and paid by Kaspi receipt), clubs and their
  Studio, news, friends, awards, the class timetable, the campus map, QR check-in on a big screen (`/show`), the
  student forum. Unofficial; Russian, Kazakh and English.
- `web/`: Svelte 5 (runes) + Vite + TypeScript, a static build served by the server.
- `server/`: Python 3, FastAPI, SQLite (WAL). The API, the Telegram bot (`bot.py`) and the nightly jobs run in one
  process. Every rule lives in `server/kbtu/logic/` (one module per area); `app.py` only routes.
- One Docker image (`Dockerfile`). **A push to `main` deploys production**: never push without the owner's yes.

## Where things are

| What | Where |
| --- | --- |
| API routes | `server/kbtu/app.py` |
| Rules by area | `server/kbtu/logic/*.py` (`core` shared helpers; `seats` sign-up and tickets; `organizing` Studio, the door; `threads` the student forum; `forum` find-people; `account` me, settings, deleting an account; `moderation` reports; `daily` nightly jobs) |
| Schema | `server/kbtu/schema.sql` + append-only `MIGRATIONS` in `server/kbtu/db.py` |
| Bot texts | `server/kbtu/texts.py` (ru, kk, en, the same placeholders in each) |
| Privacy policy, terms | `server/kbtu/i18n/legal/*.html` (Russian binding) |
| QR check-in, `/show` | `server/kbtu/checkin.py`, `web/src/screens/Screen.svelte` |
| Web entry, tabs, sheets | `web/src/App.svelte`, `web/src/lib/state/ui.svelte.ts`, `web/src/lib/state/sheets.ts` |
| API contract | `web/src/lib/api/types.ts`, `index.ts` (the interface), `client.ts` |
| UI strings | `web/src/lib/i18n/{ru,kk,en}.ts` (ru is the source; kk and en are typed against it) |
| Shared UI | `web/src/ui/` (tokens.css, base.css, glass, Sheet, Button, ...) |

## Run and check

```bash
cd web && npm ci && npm run build                     # the build fails if a bundle uses regex lookbehind (old iOS)
cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tools/qa.py --port 8790              # a seeded server; prints a signed link per made-up person
```

Before every commit, all of these pass:

```bash
cd server && .venv/bin/python -m pytest -q tests      # ~3-4 min
cd web && npm run check && npm test                   # svelte-check 0 errors, 0 warnings; vitest
```

Checking a screen: open a link `qa.py` prints, at phone size (375 px, also 320), in both themes. A hidden browser
tab freezes animations and `requestAnimationFrame`: look with it visible.

## Rules

- **English everywhere outside UI strings**: code, comments, commits, docs. UI text only in `web/src/lib/i18n/`
  (all three languages at once) and the bot's in `texts.py`. A pre-commit hook refuses Cyrillic elsewhere; in tests
  write it as `\u` escapes.
- **The database**: never edit `schema.sql`; append a migration (one transaction). A CHECK can't be altered in
  SQLite and a table rebuild with foreign keys on cascades deletes into its children: prefer a new table or column.
- **Personal data**: never in the repo, logs or screenshots. New personal data needs the privacy policy to say so
  first (a new section behind its feature flag, a new consent version); see `board_on` / `FORUM` in `app.py`.
  Deleting an account must cover every new table (`_DEL_GONE` in `logic/account.py`; a test checks the schema).
- **Speed**: a tap answers in the same frame (optimistic UI); a page never waits for its data when it opens (the
  store loads it with the app, `lib/state/data.svelte.ts`); heavy screens are lazy chunks; lists read each fact
  once for all rows, never card by card.
- **The bot** sends templates with a button into the app, never a user's words.
- **Svelte**: runes only. `@keyframes` are scoped per component: define the ones you use. The official Svelte MCP (`.mcp.json`) has the docs and
  `svelte-autofixer`: run a new or changed component through it until it reports nothing.
- **Style**: match the code around you; short comments that say why. Deliberate shortcuts are marked
  `# ponytail:` / `// ponytail:` with their ceiling and the upgrade path.
- **Security reviews**: features that touch money, check-in, anonymity or personal data get an adversarial review
  (a second agent trying to break them) before they ship.

## Feature switches (server env)

- `FORUM=1`: the find-people forum for the app's staff (`founder`: the creator alone).
- `BOARD=1`: the student forum for every student, with its privacy section and a new consent version;
  `BOARD=staff`: admins and moderators only, to try it.
- `WEB_CONCURRENCY`: uvicorn workers (the app is multi-worker safe).
