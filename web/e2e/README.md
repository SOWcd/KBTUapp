# E2E

The built app (`web/dist`) on real servers (`server/tools/qa.py`, a fresh seeded database per test), opened as qa.py's
made-up people the way Telegram opens a Mini App. `fixtures.ts` is the harness; every screen a test looks at is checked
for console errors, failed requests, sideways scroll and text out of its buttons.

## Run

```bash
cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
cd web && npm run build
npx playwright test --project=chromium-375-dark        # the flows, one browser (all 8 projects: no --project)
npm run e2e:snap                                       # the screen snapshots (needs Docker)
```

## Screen snapshots

`snap.spec.ts` takes the key screens at 375x812 in both themes (projects `snap-dark`, `snap-light`): the Afisha, an
event (with no cover, over a dark and a near-white poster, cancelled, and its end over the island), Clubs (its top, its list, and with clubs of my own), the Forum, Profile with the badge, the anthem sheet, the
assistant's welcome, the campus map, a club's Studio, the Afisha once more at 320x568, and Spy's states (from a made-up
room, its clock stopped). The clock is fixed
(Wednesday 25 Nov 2026, 10:00 in Almaty: `qa.py --now` and Playwright's clock), motion is reduced, and a picture may
differ from its baseline in `snapshots/` by 300 pixels at most. Each screen is also checked for anything running past
the screen's sides.

Pixels depend on the machine (fonts, the GPU), so the browser always comes from Playwright's own Linux image:
`e2e/linux.sh` starts it in Docker and the tests reach it over a socket, the same way locally and in CI. Without it
(`npx playwright test --project=snap-dark`) the layout checks run but no picture is compared.

**Accept an intended change** (rewrite the baselines, then commit `web/e2e/snapshots/`):

```bash
cd web && npm run build && npm run e2e:snap -- --update-snapshots
```

Without Docker (a low-memory laptop): `gh workflow run snapshots.yml --ref <branch>` retakes them all in CI;
`gh run download <run> -n snapshots -D web/e2e/snapshots` brings them back to commit.

Look at the new pictures before committing them. A new screen: a `test` in `snap.spec.ts` that calls `shot()`.

## Accessibility

`a11y.spec.ts` runs axe-core on the Afisha, Clubs, Forum and Me tabs and the event, ticket and person sheets, in the
same `snap-*` projects (375 px, both themes, the fixed clock), with the app in English. Serious and critical
violations only; a new one fails the test. What the app had when the check came in is listed in `a11y-allow.txt`, one
line per element (`<theme> <screen> <rule> <element>`). Fixed one? Strike its line: the test names lines that no
longer occur in its annotations (`a11y fixed: ...`). Never add a line for something new.

```bash
npx playwright test e2e/a11y.spec.ts --project=snap-dark --project=snap-light   # no Docker needed
```

## CI

`.github/workflows/ci.yml`, job `e2e`, on every PR that touches `web/` or `server/`: the flows in Chromium 375 dark in
two shards, and the snapshots and the a11y check beside them, and Telegram on Android (`android` project,
`android.spec.ts`: Telegram's Android launch at 360x800 on a 4x slower CPU; the tab bar under Telegram's insets, the
LOW phone's light look, a 100-post News's tap-to-frame and main-thread numbers in the job summary), all through `linux.sh`. When it fails, the run's artifact `e2e-<n>` has
`results/` (for a snapshot: `*-expected.png`, `*-actual.png`, `*-diff.png`; a trace per failed test) and the HTML
report.
