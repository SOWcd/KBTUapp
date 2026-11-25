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

## Instagram stories

Off unless `INSTAGRAM_COOKIES` names a readable file. Instagram shows stories (and some posts) only to a signed-in
account, so the bot uses the session of a spare account made for this, never anyone's own: whoever holds the file is
signed in as that account.

1. Make a new Instagram account for the bot: its own email, two-factor on, nothing personal in it. Don't follow
   private accounts with it: the bot shows whatever this account can see. Set its sensitive content control
   (Settings, Content preferences) to the strictest setting: an adult account sees stories Instagram hides from
   others, and the bot would post them to student groups.
2. Export its cookies: in a fresh browser profile or a private window, sign in to it on instagram.com, export the
   cookies of instagram.com in the Netscape `cookies.txt` format with an exporter that runs locally (yt-dlp's FAQ on
   passing cookies names some), and close the window **without signing out** (signing out ends the session the file
   holds). Export instagram.com only: other sites' lines are ignored, and a file over 256 KB is refused.
3. Put it on the server, never in the repo or the image: e.g. `/srv/kbtu-secrets/instagram/cookies.txt`, the folder
   `chmod 700`, the file `chmod 600` (`.gitignore` and `.dockerignore` skip `*cookies*.txt` as a backstop).
4. Mount the folder read-only into the container (Docker: `-v /srv/kbtu-secrets/instagram:/run/secrets/instagram:ro`;
   in Coolify, a directory mount in the app's storage) and set `INSTAGRAM_COOKIES=/run/secrets/instagram/cookies.txt`
   in the app's environment (an absolute path; `../.env` is not read for it).
   A folder, not the file itself: a replaced file then shows up in the container without a redeploy.
5. Check: a story link in a test group gets its video.

The bot reads the file at each story link and never writes it (yt-dlp gets the cookies in memory, never the file: it
would save its jar back into it). The cookies go only to instagram.com's own hosts, over HTTPS, and only to read a
story, or a post for which Instagram sent an anonymous reader to its login page (never a missing, private or
"Restricted" one); the video files are fetched without them, and Telegram never gets a link found with them. Neither
the path nor a cookie is ever logged. Only a story's video: yt-dlp skips photo stories, and highlights are not
supported.

Signed-in reads an hour, so the account reads like a person (`kbtu/tiktok.py`): 60 for all chats together, 15 for
one chat, 5 for one person; a link the session found nothing behind isn't asked again for an hour. Past a cap,
stories wait.

What members can do with it: a story read through the session shows the spare account in that story's viewer list,
so anyone in a group can make the account view anyone's public story by posting its link. And a story's video stays
in the chat, and the bot keeps its Telegram file id (until a restart), so a story can be sent again after it has
expired on Instagram.

- **Rotate** when the log says "the Instagram cookies were signed out" or "hold no session" (at most once an hour),
  and every few months anyway: export again (step 2) and replace the file.
- **Revoke**: in the spare account's settings (Accounts Center, Password and security, Where you're logged in) log
  that session out, or change the password to end every session; delete the file and unset `INSTAGRAM_COOKIES`.
  Story links are then ignored again.

## Clubs' Instagram posts

Off unless `IG_USER_ID` and `IG_TOKEN` are both set. Then every half hour the server asks Meta's Graph API (Business
Discovery) for the latest posts of each club whose links include an Instagram account (`instagram.com/<handle>`, the
club's existing social links), and each new post becomes one of the club's posts in News and on its page: the caption
as the club's own text (its first line the title), the picture (a reel's cover), the post's link as an Instagram
button (`kbtu/instagram.py`). No club signs in anywhere: the app reads through its own account. Only a club's public
**business or creator** account can be read this way; a personal account (or a wrong handle) is asked again a day
later. Nobody is notified; a link taken off the club takes its posts down. Only the club's own media is asked for
(no followers, likes or comments): nothing about people is stored.

What the owner does once:

1. **An Instagram professional account for the app** (Instagram app: Settings, Account type and tools, Switch to
   professional account, Business). It may stay empty; it only reads.
2. **A Facebook Page linked to it**: on facebook.com create a Page for the app, then in the Page's settings (Linked
   accounts, Instagram) connect the account from step 1. Business Discovery works only through an Instagram account
   linked to a Page.
3. **A Meta app**: on developers.facebook.com, My Apps, Create app, use case "Other", type **Business**. Add the
   product **Instagram** with "API setup with Facebook login" (not "with Instagram login": that one has no Business
   Discovery).
4. **Permissions**: `instagram_basic`, `pages_show_list`, `business_management` (Meta may add `pages_read_engagement`
   when it asks for them). In development mode they work at once for the app's own admins, and the app's own account
   is all we use: the token is the owner's, as an admin of the app. If Meta ever asks for **App Review** (Advanced
   Access): the use case is "read the public posts of student clubs' business accounts by their handle through
   Business Discovery and show them in the club's feed in our Telegram Mini App; no user logs in with Facebook";
   attach a screen recording of News showing such a post, and the privacy policy's address
   (`https://kbtu.sow.kz/privacy`). Business verification of the app may be asked for too.
5. **The token**: in Graph API Explorer (developers.facebook.com/tools/explorer) pick the app, "Get User Access Token"
   with the permissions of step 4, and allow the Page and the Instagram account. That token lives an hour; make it a
   long-lived one (60 days):
   `curl "https://graph.facebook.com/v24.0/oauth/access_token?grant_type=fb_exchange_token&client_id=<app id>&client_secret=<app secret>&fb_exchange_token=<short token>"`.
   Better, a **Page token that never expires**: with that long-lived user token,
   `curl "https://graph.facebook.com/v24.0/me/accounts?access_token=<long-lived token>"` lists the Page with its
   own `access_token`; use that one.
6. **The account id**: `curl "https://graph.facebook.com/v24.0/<page id>?fields=instagram_business_account&access_token=<token>"`
   gives `instagram_business_account.id` (digits, starts with 1784...).
7. Set `IG_USER_ID=<that id>` and `IG_TOKEN=<the token>` in the app's environment (Coolify), never in the repo. The
   token goes to graph.facebook.com in a request's body only and is never logged.
8. Check: a club with its Instagram link shows its latest posts in News within half an hour.

Limits: Meta allows the app 200 calls an hour per user (we are one user). A round makes at most 90 calls (one per
club account, sent 50 to a request), the least recently read accounts first, so with more than 90 linked accounts each
is read every hour or so. Usage headers past 80 %, a rate-limit error or a failed request pause the rounds (30 minutes,
doubling up to 12 hours).

- **Rotate** when the log says "IG_TOKEN was refused": make a token again (step 5) and replace `IG_TOKEN`. A user
  token expires after 60 days; a Page token made from a long-lived one doesn't, but a password change or removing
  the app from the Facebook account ends it.
- **Revoke**: remove the app in Facebook's Settings, Business integrations, and unset `IG_TOKEN`. Posts already
  brought in stay; a club's own Head+ can take any of them down in the app.

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
- `TIKTOK=1` enables captionless group replies to TikTok, YouTube Shorts, youtu.be videos under three minutes, and Instagram reels and posts (`kbtu/tiktok.py`). A post of photos, or a carousel of photos and videos, goes as one album of its first 10 items: an item that fails is left out, and its files together stay within one 50 MB upload. Instagram stories only with `INSTAGRAM_COOKIES` (below). Tikwm resolves TikTok videos and photo albums. yt-dlp resolves YouTube and Instagram. Videos use the highest compatible H.264/AAC resolution within 50 MB. Each worker caches Telegram file IDs and tries direct HTTPS files up to 20 MB before uploading. Failures are silent. All sources share `CHAT_CAP` per chat per minute and skip bots, stale messages, banned users and the forum discussion group.
- `INSTAGRAM_COOKIES=<path>`: with `TIKTOK=1`, an Instagram story's video (`instagram.com/stories/<user>/<id>`) and
  the posts Instagram keeps behind its login page for anonymous readers, through a spare account's cookies ("Instagram stories" above).
  Unset, or no readable file at the path: story links are ignored as before and nothing is requested. Read at each
  link; never logged.
- `IG_USER_ID` + `IG_TOKEN`: the clubs' Instagram posts in their news through the app's own Instagram account
  (`kbtu/instagram.py`, "Clubs' Instagram posts" above). Either unset: off, nothing is requested.
- `REPORTS=1`: clubs' event reports in Studio and the member's own log in their profile (`logic/evreports.py`). Off by default. Separate consent covers attendance marks and comments under section 3 of the privacy policy.
- `ROOMS_FILE`: the map's "Free now", the timetable's busy rooms (`server/tools/rooms.py`, default `rooms.json` next to the database); no file: off.
- `SUBJECTS_FILE`: the subjects' cards, "find people to study it with" (`server/tools/subjects.py` from the portal's course list scrape, default `subjects.json` next to the database; `logic/subjects.py`: a listing is a find-people request on a subject); no file: off.
- `PLAY_DEMO=<32+ random characters>`: Google Play's reviewer signs in at the link `admin play-demo` prints, as one
  made-up, read-only account that is never a student or staff (`android/README.md`). Unset: the link is a 404 and every
  demo session ends. Only while a review is due.
- `ANDROID_CERT_SHA256=<AA:BB:...>[,...]`: the Android app's signing certificates for `/.well-known/assetlinks.json`
  (the upload key's and Play's app signing key's); unset: no file, the app shows a browser bar.
- `WALLET_PASS_CERT` + `WALLET_PASS_KEY` + `WALLET_PASS_TYPE_ID` + `APPLE_TEAM_ID`: "Add to Apple Wallet" under My QR
  on an iPhone or a Mac (`kbtu/wallet.py`): one pass per student, their badge QR, which every event's door already
  takes; added once, never updated. The certificate is the Pass Type ID certificate followed by Apple's WWDR G4
  intermediate, both PEM; the key is its unencrypted PEM. Each value is the PEM itself (`\n` escapes are fine), a
  path to it, or its base64. Any one unset, or a key that isn't the certificate's: off (no button, `/wallet/…` is a
  404). The download link is in `/api/me` only (Safari has no session), signed with `TOKEN_KEY` over the badge's
  code: it gives what `/api/me` already gives, and dies with the code (a deleted account) or a ban. Never in the repo.
- No switch changes the policy or the consent version.
- `WEB_CONCURRENCY`: uvicorn workers (the app is multi-worker safe).

## Sponsor donations

Settings → Support accepts Telegram Stars and private receipt images/PDFs. `DONATE_PHONE` is the destination's
phone; `DONATE_RECIPIENT` must be its owner's name and initial as printed by Kaspi. Keep both in the deployment's
environment, never in source. Without a full recipient name, every receipt needs the creator's review in
Admin → Donations. Clean Kaspi receipts reuse the event checks, including file/number reuse across both features
and the same one-in-five random audit. Only a recognized Kaspi issuer heading permits automation; other banks,
missing branding and partial readings always wait for the creator. Each upload has its own private image path,
while its original file hash detects reuse across donations and event payments.

The proposed recognition rate is **1 Star = 10 KZT**; medal levels are **any confirmed amount / 5,000 / 20,000 KZT**
(`logic/donations.py`). Receipts must be at most seven days old for automatic confirmation. Images are erased
30 days after the first decision; unresolved uploads expire at 90 days. Corrections recalculate the medal.
Undo restores the earlier decision and retention deadline. The daily limit counts all five submitted receipts,
including ones already decided. Exact totals stay private. Publication of name and tier is separately opt-in and
withdrawable; this also controls whether the medal appears to other people on the profile.

New Stars invoices disclose the linked total, use version `ds1` and can only be paid by the requesting account.
Old invoice links cannot start a new payment.
Already completed legacy payments retain the earlier anonymous handling and Fuel award. They are not backfilled.

Before rollout, the owner confirms the rate, thresholds and recipient configuration, approves the Russian-binding
privacy clause with its Kazakh/English translations in `server/kbtu/i18n/legal/privacy.*.html`, and previews
`BOT.donation_confirmed`, `BOT.donation_rejected` and `STARS_INVOICE` in `server/kbtu/texts.py` in all three languages.
CI must run the server tests, Svelte check, frontend tests and build; phone review remains at 320/375 px in both themes,
including a redacted Kaspi receipt to check issuer recognition. No tests or builds were run locally for this change.
