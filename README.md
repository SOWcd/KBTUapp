# KBTU App

A Telegram Mini App for students of KBTU (Kazakh-British Technical University, Almaty): events and tickets, clubs,
news, friends, the class timetable and a campus map. It runs at [@KBTUappBot](https://t.me/KBTUappBot).
An unofficial student project, not a service of the university.

## The code is open, running a copy is not

The source is published under the [Business Source License 1.1](LICENSE): **read it, fork it, run it locally
and send pull requests**. Running it for real users (a university, a club, anyone) needs the author's written
permission: write to [@Sowers](https://t.me/Sowers). Each version becomes AGPL-3.0 four years after it is published.
This is "source-available", not open source in the OSI sense. Third-party materials: [NOTICE](NOTICE).

## How it's built

- `web/`: Svelte 5 + Vite + TypeScript, a static build.
- `server/`: Python (FastAPI) with SQLite in WAL mode: the API, the Telegram bot and the background jobs in one process.
  The schema is `server/kbtu/schema.sql` plus the migrations in `server/kbtu/db.py`.
- One Docker image (`Dockerfile`) serves both.

What the app stores and who sees it: the privacy policy at [kbtu.sow.kz/privacy](https://kbtu.sow.kz/privacy)
(the texts are in `server/kbtu/i18n/legal/`). The KBTU portal password is never stored: it is used once to sign in
and read the profile (`server/kbtu/portal.py`).

## Running it locally

No bot or real accounts needed: `qa.py` seeds a fresh database with made-up students and a club, starts the real
server with the bot off and prints a link per person that opens the app as them.

```bash
cd web && npm ci && npx vite build
cd ../server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tools/qa.py --port 8790
```

Checks: `cd server && .venv/bin/python -m pytest -q tests`, `cd web && npm run check && npm test`.

## Contributing

Ideas and fixes are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).
