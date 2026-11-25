# KBTU App for iPhone

A thin native shell over the production web app (https://kbtu.sow.kz): one `WKWebView`, so every web release reaches
the iPhone with no new build. What the shell adds, because a web page can't do it well on an iPhone (and App Review
guideline 4.2 asks for more than a website in a frame):

| | Where |
| --- | --- |
| **Sign in with Apple** (guideline 4.8), and one account reachable by Telegram or Apple | `AppleSignIn.swift`, server `logic/apple.py` |
| **Notifications** through Apple (APNs): the bot's own messages, sent to the phone instead of a second copy in Telegram | `Push.swift`, server `apns.py` |
| **A native QR scanner** at the door (a half sheet, the result above it) | `Scanner.swift` |
| **The session in the Keychain** (iOS may clear a web view's storage) | `Keychain.swift`, `WebController.swift` |

The web talks to the shell through a versioned bridge: `window.kbNative = { v, caps }` and
`webkit.messageHandlers.kb.postMessage({ cmd, ... })`, which answers with a promise (`WebController.swift`,
`web/src/lib/native.ts`). The web checks capabilities (`apple`, `push`, `scan`), never the version, and without the
bridge (Telegram, a browser) everything keeps its web way. Bump `WebController.version` with a new capability.

The app is never built on a laptop: `.github/workflows/ios.yml` does it on GitHub's Mac. XcodeGen makes the project from
`project.yml` there; the app icon is drawn from `web/public/favicon.svg`.

## What the account holder does, once

You need the Apple Developer Program (99 USD a year; an organisation account shows the organisation as the seller,
an individual one shows the person's name).

1. **The bundle ID.** developer.apple.com → Certificates, Identifiers & Profiles → Identifiers → **+** → App IDs → App.
   Bundle ID (explicit): `kz.kbtuapp` (or another; it can't change after the first upload). Tick **Push Notifications**
   and **Sign In with Apple** (Enable as a primary App ID). If you pick another ID, set it as the repository variable
   `IOS_BUNDLE_ID` (repo → Settings → Secrets and variables → Actions → Variables) and on the server.
2. **The app record.** appstoreconnect.apple.com → Apps → **+** → New App: iOS, name `KBTU App` (if taken, something
   like `KBTU App: Students`), primary language Russian, the bundle ID above, SKU `kbtuapp-ios`, full access.
3. **The App Store Connect API key** (CI signs and uploads with it). App Store Connect → Users and Access →
   Integrations → App Store Connect API → Team Keys → **+**, access **Admin** (Xcode's cloud signing needs it to make
   the distribution certificate). Download the `.p8` (only once). Add repository **secrets** (repo → Settings → Secrets
   and variables → Actions):
   - `ASC_KEY_ID`: the key's ID (10 characters);
   - `ASC_ISSUER_ID`: the Issuer ID above the keys list;
   - `ASC_KEY_P8`: the whole text of the `.p8`, from `-----BEGIN PRIVATE KEY-----` to the end line;
   - `APPLE_TEAM_ID`: developer.apple.com → Account → Membership details → Team ID.
4. **The push key** (the server sends notifications with it). Certificates, Identifiers & Profiles → Keys → **+** →
   tick Apple Push Notifications service (APNs) → download the `.p8`. On the server (Coolify) set:
   - `IOS_BUNDLE_ID=kz.kbtuapp` (turns on Sign in with Apple and push tokens; it must match the app's bundle ID);
   - `APNS_KEY_ID` (the key's ID), `APNS_TEAM_ID` (the Team ID), `APNS_KEY` (the `.p8`'s text; newlines as `\n` are fine).
   Without the `APNS_*` three, Sign in with Apple works and the bot alone sends notifications.
5. **A build.** GitHub → Actions → **iOS** → Run workflow: build `1`, version `1.0`. About 15 minutes; then App Store
   Connect → TestFlight shows the build after Apple's processing. Each next upload needs a higher build number.
   Answer TestFlight's export compliance question once: the app uses only standard HTTPS (`ITSAppUsesNonExemptEncryption`
   is already `NO`).
6. **TestFlight.** TestFlight → Internal Testing → add yourself and the team; install TestFlight on the phone. Check on
   a phone, in both themes: sign in with Telegram, sign in with Apple, link the other one in Settings → Sign-ins, allow
   notifications and get one (e.g. a reminder), the door scanner, sign out and in, kill the app and reopen it (still
   signed in).

## The App Store page

**App Privacy** (App Store Connect → App Privacy). From the privacy policy (`server/kbtu/i18n/legal/privacy.ru.html`);
no tracking, no third-party advertising or analytics SDKs. Data **linked to the user**, purpose **App Functionality**
unless said otherwise:

| Apple's category | What it is here (policy section) |
| --- | --- |
| Contact Info → Name | Telegram and KBTU names, profile (2) |
| Contact Info → Email Address | the KBTU Microsoft login and email (2) |
| Contact Info → Phone Number | optional profile phone, events that ask for it (2, 8) |
| User Content → Photos or Videos | profile photo, Gallery and albums, forum photos, payment receipts (2, 4, 5) |
| User Content → Other User Content | posts, comments, bio, appeals, find-people requests (5, 6) |
| User Content → Customer Support | appeals and questions to a person (6) |
| Identifiers → User ID | Telegram ID, Apple's ID for the app, student number (2) |
| Identifiers → Device ID | the push token (2), declared to be safe |
| Purchases → Purchase History | paid tickets (4) |
| Financial Info → Other Financial Info | Kaspi receipt images with amounts and names (4) |
| Usage Data → Product Interaction | app openings, profile views; also **Analytics** (7) |
| Other Data | the 18+ door mark, timetable, attendance and club records (3) |

Not linked to the user: anonymous feedback, aggregate usage counters. Privacy policy URL:
`https://kbtu.sow.kz/privacy`. Age rating: 12+ is likely (user-generated content with moderation and reports).

**App Review notes** (App Store Connect → the version → App Review Information). Sign-in required: yes. Paste, adjusted:

> KBTU App is an unofficial student app for Kazakh-British Technical University: events and tickets, clubs, news,
> friends, the class timetable, the campus map. It is also a Telegram Mini App; this iPhone app adds Sign in with Apple,
> push notifications, a native QR scanner for event check-in, and keeps the session in the Keychain.
>
> **Demo login:** tap **Sign in with Apple** on the first screen; no other account is needed. This makes a guest
> account: events, clubs, news, the map and Settings are open to it. Features for verified KBTU students (tickets,
> friends, the timetable) require the university's Microsoft account, which reviewers can't have; a screen recording
> of them is at <link to a short video>.
>
> Account deletion: Settings (gear on Profile) → **Delete account**. Linking Telegram: Settings → Sign-ins.
> Payments: event tickets are for real-world events, paid to the organising club outside the app (guideline 3.1.3(e)).

Optional: a fuller demo login (a verified student) as a username and password the reviewer types, the way Google Play's
reviewer gets one (`PLAY_DEMO`, PR #322), is not wired into the iPhone app yet.

## Known limits and risks

- **Guideline 5.2.1 (a third party's name):** the name and icon say "KBTU". Apple may ask for the university's
  permission. The app says it is unofficial everywhere; have a letter ready if asked.
- **Guideline 4.2 / 2.5.2:** the native parts above are the app's case; keep them working, and don't let the app
  change its purpose with web releases.
- **Two accounts are never merged.** A Telegram account that already has its own KBTU App account can't be linked to
  an account Apple made (the app says to sign in with Telegram instead); an Apple ID behind one account can't be linked
  to another. Support can sort out such a person by hand.
- ponytail: Sign in with Apple's token isn't revoked at Apple when an account is deleted (Apple asks for it with its
  REST API; that needs a client secret). The upgrade: `POST https://appleid.apple.com/auth/revoke` from `delete_me`.
- ponytail: Apple's "credential revoked" notice isn't checked at launch; the session just lives out its time.
- The Telegram sign-in button inside the app opens Telegram's page as a sheet; linking Telegram from Settings uses
  Telegram's page directly. Both need a phone check after the first build.
