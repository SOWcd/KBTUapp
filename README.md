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
  The schema is `server/kbtu/schema.sql` plus the migrations in `server/kbtu/db.py`.
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

Checks: `cd server && .venv/bin/python -m pytest -q tests`, `cd web && npm run check && npm test`.

## The assistant's documents

The university's documents never go in the repo. Rebuild: `scp -r docs/ sowcloud:<the kbtu volume>/docs-src`; in the
container `cd /app/server && python -m kbtu.docs build /var/lib/kbtu/docs-src /var/lib/kbtu/docs.db` (scans via tesseract,
embeddings with `CF_ACCOUNT_ID`/`CF_AI_TOKEN`; `.doc` → `.docx` first), delete `docs-src`; `python -m kbtu.docs audit /var/lib/kbtu/docs.db` must show no `left`; `DOCS=1` turns it on.

## Contributing

Ideas and fixes are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: [SECURITY.md](SECURITY.md).
