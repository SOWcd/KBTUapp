# End-to-end suite (issue #136)

## What was done

- **The suite.** `cd web && npm run e2e` builds the app and runs [Playwright](https://playwright.dev) 1.65.1 (`web/e2e/`, `web/playwright.config.ts`). Each spec file gets its own fresh `server/tools/qa.py` server, with a temp database on a free port. The signed links are read from its output.
- **Projects.** Four projects run by default:

  | Browser | Screen | Theme |
  | --- | --- | --- |
  | Chromium | 375x812 | dark |
  | Chromium | 320x568 | light |
  | WebKit | 375x812 | light |
  | WebKit | 320x568 | dark |

  Every browser, size and theme appears at least once, and the run stays near 5.5 minutes. `E2E_FULL=1` runs all eight combinations. Reduced motion is off, so animations run.
- **Telegram.** The real `telegram-web-app.js` reads the initData from the link. It is fetched once per run and served locally. A `TelegramWebviewProxy` stub stands in for the Telegram client. That lets a test see when the app shows or hides the BackButton and press it the way Telegram does (`back_button_pressed`). Theme params in the link follow each project's theme.
- **Ten flows**, one file each:

  | Flow | File |
  | --- | --- |
  | Student | `student.spec.ts` |
  | Friends | `friends.spec.ts` |
  | Clubs | `clubs.spec.ts` |
  | Studio | `studio.spec.ts` |
  | Door | `door.spec.ts` |
  | `/show` | `show.spec.ts` |
  | Forum | `forum.spec.ts` |
  | Settings | `settings.spec.ts` |
  | Back button | `back.spec.ts` |
  | Account deletion | `account-deletion.spec.ts` |

  Each file's header says what it walks. Where a camera is needed, the test types or sends what the camera would read.
- **Checks on every step.** `App.step()` saves a screenshot as a test attachment and runs these checks:

  | Check | On failure |
  | --- | --- |
  | Console errors | fails the test |
  | Failed requests | fails the test |
  | Horizontal scroll | fails the test |
  | Text spilling out of a button | fails the test |
  | Tap targets under 44 px | listed in an annotation and `tap-targets.txt` |
- **CI.** `.github/workflows/e2e.yml` adds a separate `e2e` job. It runs on pull requests that touch `web/` or `server/` and is non-blocking (`continue-on-error`). When it fails, it uploads the HTML report and the screenshots.
- **Seed.** `qa.py` changed in two ways:
  - Badge and ticket codes now use the formats the door reads. Before, they could not be scanned: `QA000001` is not a badge code and `QA-T2` is not a ticket code.
  - A tonight 18+ guest-list party was added, so the door's age question has someone to ask about.
- **Vitest.** `vite.config.ts` limits Vitest to `src/**/*.test.ts`, so it no longer picks up the Playwright specs.

## Bugs the suite found (each fixed in its own commit)

1. **The door scanner couldn't let in a walk-in by badge QR.** `Scanner.svelte` treated any `t.me/KBTUappBot?startapp=…` text as one of the app's own links. A badge (`u_<id>_<code>`) therefore closed the scanner and opened the person's profile, though the server accepts that exact text as a walk-in (`organizing.checkin`). Fix: badges are excluded from that shortcut.
2. **WebKit (iOS's engine) logged "ResizeObserver loop completed with undelivered notifications" each time an event sheet flew open from a poster.** `ui/fly.ts` began watching the sheet panel, an ancestor of the header, inside the first observer's callback. Fix: start that watch in the next frame. The measurement itself still happens before the first paint.
3. **A new friend was missing from an event's "friends going" until the app was relaunched.** `friendsChanged()` reloaded friends and `/me`, but not the Afisha's events, and the event sheet reads "friends going" from those events. Fix: also reload the Afisha.
4. **A club's page showed no recruitment round for up to 15 s after the round opened.** The server caches the shared club list for 15 s (`SHARED_TTL`), and `ClubSheet` used that copy even after fetching the club itself. During that window "Apply" sent an ordinary join request. Fix: the round comes from the club's own copy when the list's is stale. The list's copy is still used while both have the round, because it carries the optimistic "applied".

## Noted, not changed

- **`POST /api/ms/claim` answers 403 on every launch.** For anyone without a pending Microsoft sign-in, this is the API's "nothing waits" answer, and `test_core` tests it as such. The suite allow-lists it (`EXPECTED` in `fixtures.ts`). A 204 would keep a red line out of every launch's console. Left for the owner, since it changes a tested API contract.
- **Tap targets under 44 px are common.** Most are 36 px round icon buttons (Share, Save, Settings, Map), the week strip's day buttons (41x66), the Afisha chips (about 98x29) and the "All" link (48x20). This is reported only, per the issue.
- **Studio's pre-publish check doesn't list missing seats.** The missing seats field is required, but the check lists only "no cover / no description". "Publish anyway" then closes silently and marks the field red. This is a UX question.
- **The co-host picker only lists clubs from the main catalog.** A new club below the size bar can't be invited from the editor, so the Studio flow sends the invite through the API. Is that intended?
- **Kept quiet by the harness, not tested:**
  - The home-screen offer, which shows once per phone and can't be closed for 5 s, is marked seen before launch.
  - WebKit's failed read of a `blob:` the install sheet revoked on close is ignored.
- **One WebKit student run failed once with a console error under heavy local load.** It did not reproduce in more than ten later runs. CI retries once.

## Verification

- `cd web && npm run e2e`: 60 passed in 5.5 min on a MacBook (4 projects × 15 tests) in the last two full runs; the run before them had the one WebKit flake above.
- `npm run check`: 0 errors, 0 warnings. `npm test`: 347 passed. `npm run build`: passes.
- `pytest -q -n auto tests`: 1599 passed and 4 failed.
  - `test_tag_all` and `test_tiktok` failed only while the e2e suite ran in parallel; they pass alone.
  - `test_event_doc` (2 tests) fails the same way on an untouched `main` on this macOS machine. It is environmental: no LibreOffice or tesseract here.
- Not done: running the changed components through the Svelte MCP autofixer (not available in this environment), and checking on a real iPhone.
