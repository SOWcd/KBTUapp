# KBTU App

A Telegram Mini App for students of KBTU (Kazakh-British Technical University, Almaty): events and tickets, clubs,
news, friends, the class timetable and a campus map. It runs at [@KBTUappBot](https://t.me/KBTUappBot).
An unofficial student project, not a service of the university.

## Author

Made by Sukhrab Nurmatov (**SOWER**), a KBTU student. Questions, ideas, bugs or just hello:
Telegram [@Sowers](https://t.me/Sowers) · GitHub [@SOWcd](https://github.com/SOWcd) · [sow.kz](https://sow.kz).

## The code is open, running a copy is not

The source is published under the [Business Source License 1.1](LICENSE): **read it, fork it, run it locally
and send pull requests**. Running it for real users (a university, a club, anyone) needs the author's written
permission: write to [@Sowers](https://t.me/Sowers). Each version becomes AGPL-3.0 four years after it is published.
This is "source-available", not open source in the OSI sense. Third-party materials: [NOTICE](NOTICE).

## How it's built

- `web/`: Svelte 5 + Vite + TypeScript, a static build.
- `server/`: Python (FastAPI) with SQLite in WAL mode: the API, the Telegram bot and the background jobs in one process.
  The schema is `server/kbtu/schema.sql` plus the migrations in `server/kbtu/migrations.py`.
- One Docker image (`Dockerfile`) serves both.

What the app stores and who sees it: the privacy policy at [kbtu.sow.kz/privacy](https://kbtu.sow.kz/privacy)
(the texts are in `server/kbtu/i18n/legal/`). The app never asks for the KBTU portal password: students type their
name, student ID and year, marked unconfirmed until the KBTU account is confirmed.

## Running it locally

No bot or real accounts needed: `qa.py` seeds a fresh database with made-up students and a club, starts the real
server with the bot off and prints a link per person that opens the app as them.

Node 22, Python 3.14 (as the `Dockerfile`).

```bash
cd web && npm ci && npx vite build
cd ../server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tools/qa.py --port 8790
```

Checks: `cd server && .venv/bin/python -m pytest -q -n auto tests`, `cd web && npm run check && npm test`.

## The assistant's documents

The university's documents never go in the repo. Rebuild: `scp -r docs/ sowcloud:<the kbtu volume>/docs-src`; in the
container `cd /app/server && python -m kbtu.docs build /var/lib/kbtu/docs-src /var/lib/kbtu/docs.db` (scans via tesseract,
embeddings with `CF_ACCOUNT_ID`/`CF_AI_TOKEN`; `.doc` → `.docx` first), delete `docs-src`; `python -m kbtu.docs audit /var/lib/kbtu/docs.db` must show no `left`; `DOCS=1` turns it on.
Curricula: any file whose path has "RUP" (Latin or Cyrillic) is read as a table, one chunk per semester; the year in its
name, else its folder's, is the intake.

## Free rooms on the map

The timetable scrape never goes in the repo. `python3 -I server/tools/rooms.py <progress.json> rooms.json` (busy hours by
room only), copy it next to the database (`/var/lib/kbtu/rooms.json`) or point `ROOMS_FILE` at it; no file: no "Free now".
`python3 -I server/tools/subjects.py <course-list.json> subjects.json` (names, codes, credits, school only), next to the database or
`SUBJECTS_FILE`; no file: no subjects' cards.

## Contributing

Ideas and fixes are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).

## Feature switches

- `FORUM=1`: the find-people forum for the app's staff (`founder`: the creator alone).
- `BOARD=1`: the assistant, sign-up questions, the map's flaws for every student; `BOARD=staff`: admins and
  moderators only. Its old in-app forum is off for good.
- `NEWS_CHANNEL`: the news channel (default `@KBTUevents`; the old name `EVENTS_CHANNEL` still read).
- `FORUM_CHANNEL=<chat id>`: the forum channel: students post from the app, the bot publishes (`logic/fchannel.py`).
  `FORUM_GROUP`: its discussion group.
- `DOCS=1`: the assistant answers from the university's documents (`kbtu/docs.py`, a separate file at `DOCS_DB`, default
  next to the database; built by hand, README). Production runs `DOCS=1` (no new recipient). `DOCS=hybrid` (the question's
  embedding from Cloudflare too) waits for its clause in the privacy policy's section 5 (Codex's) and a consent version.
- `TIKTOK=1` enables captionless group replies to TikTok, YouTube Shorts, youtu.be videos under three minutes, and Instagram reels and video posts (`kbtu/tiktok.py`). Tikwm resolves TikTok videos and photo albums. yt-dlp resolves YouTube and Instagram. Videos use the highest compatible H.264/AAC resolution within 50 MB. Each worker caches Telegram file IDs and tries direct HTTPS files up to 20 MB before uploading. Failures are silent. All sources share `CHAT_CAP` per chat per minute and skip bots, stale messages, banned users and the forum discussion group.
- `REPORTS=1`: clubs' event reports in Studio and the member's own log in their profile (`logic/evreports.py`). Off by default. Separate consent covers attendance marks and comments under section 3 of the privacy policy.
- `ROOMS_FILE`: the map's "Free now", the timetable's busy rooms (`server/tools/rooms.py`, default `rooms.json` next to the database); no file: off.
- `SUBJECTS_FILE`: the subjects' cards, "find people to study it with" (`server/tools/subjects.py` from the portal's course list scrape, default `subjects.json` next to the database; `logic/subjects.py`: a listing is a find-people request on a subject); no file: off.
- No switch changes the policy or the consent version.
- `WEB_CONCURRENCY`: uvicorn workers (the app is multi-worker safe).
