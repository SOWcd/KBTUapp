---
name: ship
description: Ship a change to KBTU App: branch in a worktree, run the gate, open a PR, wait for CI, merge (main deploys production).
---

1. `git fetch origin && git worktree add -b <name> ../KBTUapp-<name> origin/main`; link `web/node_modules` and `server/.venv` from the main checkout.
2. Work there. Gate before committing (AGENTS.md "Run and check"): `cd server && .venv/bin/python -m pytest -q -n auto tests`; `cd web && npm run check && npm test`. A new migration: also `server/tools/schema_dump.py`.
3. Commit in English (no Cyrillic outside i18n/texts.py; the hook checks), push the branch, `gh pr create` (what changed, why, the gate's result, what was not verified).
4. `gh pr checks <n> --watch`; red: read `gh run view <id> --log-failed`, fix, push.
5. Green: `gh pr merge <n> --squash`. Main deploys production in a few minutes (Coolify).
Conflicts with main in i18n files: keep main's lines, add the branch's new keys.
