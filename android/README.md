# KBTU App for Android (Google Play)

The Android app is a Trusted Web Activity (TWA): a thin Chrome shell that opens https://kbtu.sow.kz full screen, with
no browser bar, once the site vouches for the app in `/.well-known/assetlinks.json`. There is no Android code in the
repository: Bubblewrap generates the project from [`twa-manifest.json`](twa-manifest.json) in GitHub Actions
([`.github/workflows/android.yml`](../.github/workflows/android.yml)), which builds and signs the `.aab`. Every web
release reaches the Android app at once; a new `.aab` is needed only when `twa-manifest.json` changes (name, icon,
colours) or Play asks for a newer target SDK.

- Package id: `kz.sow.kbtu` (reverse-domain, from kbtu.sow.kz; the same as the iPhone app's bundle ID), fixed for good
  after the first upload. It must match `ANDROID_PACKAGE` in `server/kbtu/app.py` (assetlinks.json).
- Icon: `web/public/icon-512.png`, also as the maskable (adaptive) icon (the launcher's only; never on the splash).
- Colours: each theme's ground, the `#boot` colours in `web/index.html` (`#F2F2F7` light, `#000000` dark; change them
  together). The splash is that bare ground, no logo (owner, Nov 25): the workflow swaps Bubblewrap's icon picture for
  an empty one and gives `backgroundColor` its dark twin (`values-night`, which the manifest has no field for), so the
  web's own boot screen, a different one each launch, comes up on it with no seam. The phone's theme picks it: someone
  who chose the other one in the app sees the ground change as the page paints.
- Sign-in: Telegram Login in the browser, as on the web (`logic/web_auth.py`); students then verify with Microsoft.

## Once: the upload key and the two secrets

On your own computer (never in the repo, never in a chat), with a JDK installed:

```bash
keytool -genkeypair -keystore kbtuapp-upload.jks -storetype PKCS12 -alias upload -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=KBTU App"
base64 -w0 kbtuapp-upload.jks        # macOS: base64 -i kbtuapp-upload.jks
```

GitHub → the repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
| --- | --- |
| `ANDROID_UPLOAD_KEYSTORE` | the one line `base64` printed |
| `ANDROID_UPLOAD_PASSWORD` | the password keytool asked for (the store's and the key's) |

Keep `kbtuapp-upload.jks` and its password in a password manager. If it is ever lost, Play Console can reset the
upload key (Play keeps the app signing key itself).

## Each release: build the .aab

GitHub → Actions → Android → Run workflow, on `main`: `version_code` a whole number bigger than any uploaded before
(1, 2, 3...), `version_name` e.g. `1.0.0`. When it's green, download the artifact `kbtuapp-<code>` (a zip with
`kbtuapp-<code>.aab`). The log's last step prints the upload certificate's `SHA256:` fingerprint.

## The server: assetlinks.json

In Coolify, set and redeploy:

```
ANDROID_CERT_SHA256=<upload key SHA-256>,<app signing key SHA-256>
```

- the upload key's: from the workflow's log (above);
- Play's app signing key's: Play Console → the app → Test and release → Setup → App integrity → App signing →
  "App signing key certificate" → SHA-256 (there after the first upload).

Check: https://kbtu.sow.kz/.well-known/assetlinks.json lists both. Without the Play one, the app installed from Play
shows a browser bar at the top: that's the sign it is missing or wrong.

## The reviewer's demo login (App access; the App Store's too)

The stores' reviewers have no Telegram. One switch serves both stores: `PLAY_DEMO`, a code. The sign-in page shows a
small, visible **Sign in with a code** under the Telegram button (never a hidden door: App Review 2.5.19); the code
typed there, or the link below, opens the demo account. While a review is due:

1. Coolify: `PLAY_DEMO=<32+ random characters>` (`python3 -c 'import secrets;print(secrets.token_urlsafe(32))'`), redeploy.
2. `admin play-demo` (through the prod gate) prints the link `https://kbtu.sow.kz/play-demo?k=<code>`; the part after
   `k=` is the code.
3. Something to see: make a free event in your own club for the review weeks (`admin event-new`, or Studio), then
   `admin play-demo seed <event id> [<event id>]`: the demo account holds a ticket with its QR to each. Its door list
   shows "Demo Reviewer"; nobody gets a message. After the review: `admin play-demo unseed`.
4. Play Console → App content → App access → "All or some functionality is restricted" → add instructions
   (App Store Connect → App Review Information: the same text, and a screenshot of the ticket's QR as the sample QR):

   > Name: Demo access. The app signs in with Telegram, which reviewers may not have. On the sign-in screen, tap
   > "Sign in with a code" and enter: <code>. (Or open https://kbtu.sow.kz/play-demo?k=<code> on the test device.) It
   > opens KBTU App as a demo account (made-up name "Demo Reviewer") with tickets to two events: open one in Afisha to
   > see its QR code, which the organizers scan at the door. The demo can browse events, clubs, news, the timetable
   > page and the campus map; it is read-only. Verifying as a KBTU student needs a university Microsoft account and
   > is not available to the demo. The code works for as long as the review lasts, from any country.

What the demo account is: one made-up user (no student row, no role, the bot never writes to it) that can only read
the catalogue routes listed in `web_auth.DEMO_READS`: no people, no writes. After the review: remove `PLAY_DEMO` (the
link answers 404, and the redeploy deletes every demo session, so turning it on again later revives none). To
change the link instead: a new `PLAY_DEMO`, then `admin play-demo revoke` (it never refuses, whatever the demo row
says). A browser already signed in as a real person keeps that session: the link opens the demo only in a fresh
profile (or after signing out).

## Play Console: the first release

A personal developer account (made after Nov 2023) must run a closed test with at least **12 testers opted in for
14 days in a row** before it may apply for production.

1. Create app: name `KBTU App`, default language English (United States), App, Free.
2. App content (Policy → App content), all of it:
   - Privacy policy: `https://kbtu.sow.kz/privacy?lang=en`
   - App access: the demo login above.
   - Ads: no ads.
   - Content rating: the questionnaire (category: Social or communication; user interaction yes: users talk to each
     other and share content; no violence, no gambling).
   - Target audience: 16–17 and 18 and over (university students; nothing aimed at children).
   - News app: no. Government app: no. Financial features: none (tickets are paid by Kaspi transfer outside the app;
     the app holds no money).
   - Data safety: the answers below.
   - Account deletion URL: `https://kbtu.sow.kz/delete?lang=en` (public: in the app, Settings → Delete account; or
     ask @Sowers; what stays links to the policy). The App Store listing can give the same page.
3. Store listing: the texts in [listing.md](listing.md) (en and ru), the 512×512 icon (`web/public/icon-512.png`),
   a 1024×500 feature graphic, and 2–8 phone screenshots (take them in both themes at phone size, from the app
   installed from Play: tickets, the map, the timetable, the scanner; no browser bar, no university crest). Category:
   **Education** or **Social**, never News (that brings Play's News declaration).
4. Test and release → Testing → Closed testing → Create track → Testers: an email list of Google accounts. Aim for
   about **20 real students** (the rule's 12 plus margin: a tester who leaves early doesn't count), found through the
   bot or a club chat, each with an Android phone and a Google account. Create release → upload `kbtuapp-<code>.aab`
   → Release notes → Roll out. Send the testers the opt-in link from the track's Testers tab; each one opts in and
   installs from Play (not a copy sent by hand: only Play's install shows whether assetlinks.json holds Play's key).
5. The test itself, **14 days in a row** at least (Google refuses production for weak tests: "testers were not
   engaged"):
   - day 1: check on a tester's phone that the app installed from Play opens with no browser bar;
   - ask the testers to use it for real on several days: their tickets, the timetable, the map, a club, the forum;
   - ship **2–3 updates** during the test (a fix or a small change each; a new `.aab` needs a bigger `version_code`);
   - collect feedback in the app (Profile → the app's card → "What's wrong?") and note what changed because of it:
     the form asks.
6. Dashboard → Apply for production. Answer concretely (Google reads it): who the testers were (KBTU students, how
   many, how found), what they used and how often, how feedback was gathered (the in-app form, the bot) and what
   changed after it, who the app is for ("students of one university in Almaty, unofficial, 16+"), and why it's
   ready. Wait for review (often several days), then Production → Create release with the same or a newer `.aab`.
   Refused: Google asks for 14 more days; run them the same way and apply again.

Things a reviewer may question, answered in advance:

- The name holds the university's name: the listing and the app say it is unofficial and independent (impersonation policy).
- Paid tickets: physical event entry, paid outside Play by Kaspi transfer: outside Play Billing's scope. Never sell
  anything digital in the app (premium features, paid badges, coins): that would need Play Billing.
- User-generated content (forum, comments, profiles, friends): terms accepted before posting, Report on every post and
  profile, **Block** on every person's card (any avatar opens it: friends end, no requests either way, gone from each
  other's forum), moderators in the Admin sheet, the contact (@Sowers) on Profile's app card and in the policy.
- Notifications: `enableNotifications` stays `false`: the app's reminders come from the Telegram bot, and the site
  sends no web push, so Bubblewrap's notification delegation would ask for a permission it never uses.
- "Support the app" (Settings, when `DONATE_PHONE` is set) is a voluntary Kaspi transfer to the creator. Play treats
  tipping a developer as digital: if a reviewer objects, the row has to stay hidden in the Android app.

## Data safety answers

Derived from the privacy policy (`server/kbtu/i18n/legal/privacy.en.html`, the revision of 22 Nov 2026); re-check
them whenever the policy changes. General answers:

- Does the app collect or share any of the required user data types? **Yes.**
- Is all user data encrypted in transit? **Yes** (HTTPS only; section 12).
- Do you provide a way for users to request that their data is deleted? **Yes** (Settings → Delete account; @Sowers).

Collected (all **processed**, none **ephemeral**; purposes **App functionality** and **Account management** unless
noted; none for advertising or marketing):

| Category → type | Required? | From the policy |
| --- | --- | --- |
| Personal info → Name | Required | Telegram names (§2); students' full names from Microsoft (§2) |
| Personal info → Email address | Optional | Microsoft verification (§2), students only |
| Personal info → User IDs | Required | Telegram ID; student number (§2) |
| Personal info → Phone number | Optional | profile, lists, events that ask for it (§2, §8) |
| Personal info → Other info | Optional | year, school, city, bio, nickname, "18 or older" door mark (§2, §3) |
| Financial info → Purchase history | Optional | Kaspi receipts for paid tickets: amount, number, names, time (§4) |
| Location → Approximate location | Optional | a Gallery photo's place label (main building, building 2, dorm, off campus); the coordinates stay on the device (§5) |
| Messages → Other in-app messages | Optional | comments, Secret Santa chat, appeals and questions to a person (§3, §5, §6) |
| Photos and videos → Photos | Optional | profile photo, Gallery, forum photos, receipt images (§2, §4, §5) |
| Files and docs | Optional | an event's PDF from organizers (§5) |
| App activity → App interactions | Required | openings, profile views, staff actions (§7); also **Analytics** (counters, §7) |
| App activity → Other user-generated content | Optional | posts, bio, answers, reviews, timetable, map notes, KRI questions (§3, §5, §6) |
| App info and performance → Diagnostics | Required | technical logs: time, address, errors (§7); purpose **App functionality** and **Fraud prevention, security, and compliance** |

Not collected: precise location, contacts, calendar, health, audio, web history, installed apps, device or advertising IDs.

Shared (Play's meaning: to a third party that is not a service provider acting for us): **No**, with one caution.
Telegram, Microsoft, Cloudflare and the AI hosts (§9) act as processors for us, and forum posts are published at the
user's own request; neither counts as sharing. The caution: on its free tier Google's Gemini API may use request
content to improve its products (§9). If Google answers KRI's questions on the free tier, declare **App activity →
Other user-generated content** as **Shared**, purpose **App functionality**.
