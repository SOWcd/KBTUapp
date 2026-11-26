#!/bin/sh
# `playwright test` with the browsers from Playwright's own Linux image, so a Mac and CI see the same pixels (the
# screen snapshots, e2e/snap.spec.ts); the app and its qa.py servers run here, the browser reaches them through
# Playwright (exposeNetwork). Arguments go to `playwright test`:
#   npm run e2e:snap -- --update-snapshots      accept the new pictures (e2e/README.md)
set -e
cd "$(dirname "$0")/.."
v=$(node -p "require('@playwright/test/package.json').version")
port=${PW_PORT:-3555}
id=$(docker run -d --rm --init --ipc=host -p "127.0.0.1:$port:3000" --user pwuser --workdir /home/pwuser \
  "mcr.microsoft.com/playwright:v$v-noble" npx -y "playwright@$v" run-server --port 3000 --host 0.0.0.0)
trap 'docker stop "$id" >/dev/null' EXIT INT TERM
i=0
until docker logs "$id" 2>&1 | grep -q "Listening on"; do
  i=$((i + 1)); [ "$i" -gt 120 ] && { docker logs "$id"; exit 1; }
  sleep 1
done
PW_WS="ws://127.0.0.1:$port/" npx playwright test "$@"
