# KBTU App for iPhone

A thin native shell over the production web app (https://kbtu.sow.kz): one `WKWebView`, so every web release reaches
the iPhone with no new build. What the shell adds, because a web page can't do it well on an iPhone (and App Review
guideline 4.2 asks for more than a website in a frame):

| | Where |
| --- | --- |
| **Sign in with Apple** (guideline 4.8), and one account reachable by Telegram or Apple | `AppleSignIn.swift`, server `logic/apple.py` |
| **Notifications** through Apple (APNs): the bot's own messages, sent to the phone instead of a second copy in Telegram | `Push.swift`, server `apns.py` |
| **A native QR scanner** at the door (a half sheet, the result above it) | `Scanner.swift` |
| **A native tab bar** (`UITabBar`, SF Symbols): the web's tabs, titles and dots; a tap switches the web's tab through the bridge, the web's own bar hides (`data-ntabs`) | `WebController.swift`, web `lib/native.ts` `nativeTabs` |
| **A bundled offline screen** when the site can't load (no network, our server down), with **my tickets' QR codes** drawn natively, so the door scans them with no network | `OfflineView.swift`, `Tickets.swift`, web `nativeTickets` |
| **Telegram sign-in and linking** in the system's sign-in sheet (`ASWebAuthenticationSession`), back through the server's `/tg-back` | `TelegramLink.swift`, server `logic/apple.py` |
| **The session in the Keychain** (iOS may clear a web view's storage) | `Keychain.swift`, `WebController.swift` |

The web talks to the shell through a versioned bridge: `window.kbNative = { v, caps }` and
`webkit.messageHandlers.kb.postMessage({ cmd, ... })`, which answers with a promise (`WebController.swift`,
`web/src/lib/native.ts`). The web checks capabilities (`apple`, `push`, `scan`, `tabs`, `tickets`, `tglink`), never the version, and
without the bridge (Telegram, a browser) everything keeps its web way. Bump `WebController.version` with a new
capability.

**The bridge is bound to our domain** (App Store 4.7.2): `WKAppBoundDomains` is `kbtu.sow.kz` (and `t.me`, only for the
news' embedded Telegram posts) with `limitsNavigationsToAppBoundDomains`, so the web view never navigates elsewhere
(other links open in Safari's sheet or their own app, `window.open` never makes a second web view), and the bridge
answers only our site's main frame over https in this one web view. `tglink` opens only `https://oauth.telegram.org`.

The app is never built on a laptop: `.github/workflows/ios.yml` does it on GitHub's Mac. XcodeGen makes the project from
`project.yml` there; the app icon is drawn from `web/public/favicon.svg`.

The launch screen is the web boot screen's bare ground, no logo (owner, Nov 25): the `Ground` colour (`#F2F2F7` light,
`#000000` dark, the very `#boot` colours in `web/index.html`; change them together), which also lies under the page
until it paints, so the web's own boot screen, a different one each launch, comes up on it with no seam. iOS draws it
in the phone's theme: someone who picked the other one in the app sees the ground change as the page paints.

## What the account holder does, once

You need the Apple Developer Program (99 USD a year; an organisation account shows the organisation as the seller,
an individual one shows the person's name).

1. **The bundle ID.** developer.apple.com → Certificates, Identifiers & Profiles → Identifiers → **+** → App IDs → App.
   Bundle ID (explicit): `kz.sow.kbtu` (reverse-domain from kbtu.sow.kz, the same as the Android package; it can't
   change after the first upload). Tick **Push Notifications**
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
   - `IOS_BUNDLE_ID=kz.sow.kbtu` (turns on Sign in with Apple and push tokens; it must match the app's bundle ID);
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
> friends, the class timetable, the campus map. It is also a Telegram Mini App; this iPhone app adds a native tab bar,
> Sign in with Apple, push notifications, a native QR scanner for event check-in, a native offline screen that keeps
> the person's own event tickets (their QR codes) usable with no network, Telegram sign-in through the system's
> sign-in sheet, and keeps the session in the Keychain. Content loads from our own server (kbtu.sow.kz); the native
> bridge is limited to that domain.
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
- Telegram's sign-in (the entrance) and linking (Settings → Sign-ins) open Telegram's page in the system's sign-in sheet;
  both need a phone check after the first build. The offline screen: turn on Airplane mode with a ticket, kill and
  reopen the app.
- The tab bar is the classic 49 pt `UITabBar` of the iOS 18 SDK (`macos-15` runner); the web's `--nav-h` in the app is
  49 px to match (`tokens.css` `data-ntabs`). A build with the iOS 26 SDK draws Apple's floating bar: check that the
  pages still end above it.
