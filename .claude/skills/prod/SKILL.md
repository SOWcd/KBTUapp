---
name: prod
description: Run a command against production KBTU App through the gated ssh (admin CLI, read-only SQL, logs). Use for importing a guest list, creating a quiet event, drawing groups, checking data on prod.
---

Production is reached only through `ssh claude-kbtu <verb>`; every call is logged.

- `ssh claude-kbtu query` + SQL on stdin: read-only, ONE statement per call (`echo "SELECT ..." | ssh claude-kbtu query`). Schema: `server/kbtu/schema.current.sql`.
- `ssh claude-kbtu logs`: recent server log.
- `ssh claude-kbtu admin <args>`: `python -m kbtu.admin <args>`; the full list is the docstring at the top of `server/kbtu/admin.py`.
  The gate passes arguments only, never stdin: a file input (`guests`, `event-new`) goes as `--gz <base64 of gzip>` at the end:
  `ssh claude-kbtu admin guests <event id> --gz "$(gzip -c list.csv | base64 -w0)"`.
  Guest CSV header: `student_id,adult,username,name` (adult 1/0/empty). Import is additive (upsert), never removes anyone.
- If it prints a Cloudflare Access URL: keep the ssh running and approve the login yourself in the browser (GitHub); never ask the owner.

Rules: personal data never goes into the repo, logs or screenshots; print counts, not people. A write the organizer didn't ask for (e.g. redrawing groups) overwrites their work: ask first.
