<script lang="ts">
  // App shell: the tabs (one scrolling screen each; what used to be their other pages opens as a sheet), the capsule on
  // top, the nav at the bottom, one overlay stack for sheets. Telegram's Back button closes the top overlay.
  import { onMount, untrack, type Component } from 'svelte';
  import { setLucideProps } from '@lucide/svelte/context';
  import { ui, TABS, overlays, open, close, say, moment, backTo, goTab, here, type Tab } from './lib/state/ui.svelte';
  import { native, nativeTabs, nativeTickets } from './lib/native';
  import { may } from './lib/perms';
  import { fresh } from './lib/state/assistant.svelte';
  import { session, loadMe, setLoginHook, asStudent, takeAgain, runningCheckin } from './lib/state/session.svelte';
  import { CONSENT_VOL } from './lib/legal';
  import { askAfterTeamMark } from './lib/reports';
  import { readCache, writeCache } from './lib/state/cache';
  import { keepTickets } from './lib/offlineTickets';
  import { channel, channelUnread, warmChannelFeeds, watchChannelVisit } from './lib/state/channel.svelte';
  import { loadSubjects, subjReady } from './lib/state/subjects.svelte';
  import { data, resetResearch, loadResearch, loadResearchRequests, loadAfisha, loadSchedule, loadCredits, loadSupport, loadGallery, loadFriends, loadMyCard, loadNews, loadInbox, loadRegistry, loadVol, loadAppeals, loadLibrary, loadSg, loadAsks, loadHelpq, loadStudio, loadTeam, loadMeetups, loadMeetupSetup, phrase, studioChanged, eventById, eventTeamChunk, toggleGoing, skipped, classKey } from './lib/state/data.svelte';
  import { burst } from './ui/burst';
  import { hiNow, nextUp, once, opened, returning, seen } from './lib/greet';
  import { visit } from './lib/helpus';
  import { nameOf } from './lib/short';
  import { sheets } from './lib/state/sheets';
  import { i18n, t, subjectOf } from './lib/i18n/index.svelte';
  import { classEmoji } from './lib/i18n/subjects';
  import { classesLeft } from './lib/classes';
  import { backButton, haptic, inTelegram, on, onAndroid, onComputer, onIos, openLink, requestWriteAccess, tg } from './lib/tg';
  import { deskRegistry } from './lib/desk';
  import { api, ApiErr, localize, onFail } from './lib/api';
  import { dayNo, nowTs, time, at } from './lib/time';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import Ban from '@lucide/svelte/icons/ban';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import Nav from './ui/Nav.svelte';
  import Capsule, { type Live } from './ui/Capsule.svelte';
  import { anthem } from './lib/state/anthem.svelte';
  import { TAB_ICON } from './ui/icons';
  import KbtuMark from './ui/KbtuMark.svelte';
  import Toast from './ui/Toast.svelte';
  import { feedChrome, unfeed } from './ui/chrome';
  import ListPage from './screens/afisha/List.svelte';
  import type { CiKind } from './screens/sheets/CheckinResult.svelte';
  import { warmMap } from './lib/map';
  // after lib/map: imported before it, the map's place names (i18n/spots) became a chunk of their own at the start
  import { chunks, dropLazy, lazy, openCheckin, openDeepLink, warm } from './lib/state/openers';
  import { count, crashed, launchedFrom, painted, timed } from './lib/stats';
  import { offerDue } from './lib/androidTest';
  let { standaloneBar: StandaloneBar }: { standaloneBar?: Component<{ back: boolean; tint?: string | null }> } = $props();
  setLucideProps({ size: 22, strokeWidth: 2 }); // stroke 2 everywhere (the design system, Oct 30; was 1.9)

  // sheets reachable from anywhere: their openers are lib/state/openers.ts; App sets the few that need its state or its
  // own components (login, ask, askText, assistant, consent, registry, celebrate, deepLink)
  const settingsList = () => import('./screens/profile/SettingsList.svelte'); // the settings under my lanyard (Me)
  const channelPage = () => import('./screens/forum/Channel.svelte'); // the forum: posts to the public channel, its own tab (Nov 1)
  // tabs in chunks of their own, out of the start's bundle (the Afisha opens first): Profile, with the lanyards' art (Hero,
  // LanyardBand, ClubScene), was a fifth of the start's code and 41 kB of its CSS; Clubs, the catalogue, ~13 kB gzip more.
  // their chunks are warmed once the first tab is drawn
  const tabPages: Partial<Record<Tab, () => Promise<{ default: Component }>>> = {
    forum: channelPage,
    club: () => import('./screens/afisha/Clubs.svelte'),
    profile: () => import('./screens/profile/Me.svelte'),
  };
  const pages = $state<Partial<Record<Tab, Component>>>({});
  const pageLoads: Partial<Record<Tab, Promise<void>>> = {};
  const pageReady = (k: Tab) => !tabPages[k] || !!pages[k];
  function loadPage(k: Tab): Promise<void> {
    const load = tabPages[k];
    if (!load || pages[k]) return Promise.resolve();
    return (pageLoads[k] ??= load().then((m) => { pages[k] = m.default; }, (e) => { delete pageLoads[k]; throw e; }));
  }
  // the policy changed since this student agreed: nobody is asked on opening the app (owner, Nov 13); the gate comes
  // when they do what the server holds for the policy in force (a post, the assistant: api "forbidden"/"consent" ->
  // sheets.consent), and may be declined. Staff and students added by hand have no consent of theirs; a deletion
  // pending is exempt. Only on the server's word (boardKnown): the launch copy's policy is the default, not the one in force.
  let asked = $state(false);
  const consentGate = () => import('./screens/ConsentGate.svelte');
  const gated = $derived.by(() => {
    const s = session.me?.student;
    return !!s && session.boardKnown && !session.me?.deleteAt && asked && !['staff', 'admin', session.policy, session.policy + CONSENT_VOL].includes(s.consent);
  });
  $effect(() => { ui.gate = gated; });
  // a club's Studio pane and its Team are chunks: fetch them ahead, so they open in the tap's frame;
  // the Feed, News, Friends and the settings list too (pages once, sheets now), so they open in the tap's frame
  $effect(() => { if (data.events.some((e) => e.teamMax) || data.past.some((e) => e.teamMax)) void eventTeamChunk().catch(() => {}); });
  const warmPages = () => { [chunks.feed, chunks.news, chunks.friends, settingsList, chunks.people, chunks.photos, chunks.album, chunks.gallery].forEach(warm); if (session.me?.bigScreen) warm(chunks.screen); if (!session.me?.memberships.length) return; warm(chunks.studio); warm(chunks.team); };
  // the forum's chunk and its feed with the app, so the tab opens full (the speed rule)
  const warmChannel = () => { if (!session.channel) return; void loadPage('forum').catch(() => {}); warmChannelFeeds(); warm(chunks.research); warm(chunks.researchForm); warm(chunks.researchPropose); };
  // the subjects' list with the app (the Forum tab's row, my timetable's classes open their card in the tap's frame)
  const warmSubjects = () => { if (subjReady()) idle(() => { void loadSubjects(); void import('./screens/subjects/Subjects.svelte'); void import('./screens/subjects/Subject.svelte'); }); };
  // one sign-in sheet at a time, and none once Microsoft has confirmed me: a second one (Microsoft's return opening its
  // own over the waiting one) stayed under the first and asked a new student to sign in with Microsoft again (Nov 14)
  // The sign-in sheet and the question sheet are chunks with the Sheet they draw on: the first Afisha frame needs neither
  // (issue 339). They are fetched right after the first paint (warmNavigation), so a tap opens them in its frame.
  let Login: Component<any> | null = null;
  const loginSheet = () => import('./screens/sheets/LoginSheet.svelte').then((m) => (Login = m.default));
  const askSheet = () => import('./ui/Ask.svelte').then((m) => m.default);
  const offline = () => say(t('common.offline'), 'pleading_face_3d');
  sheets.login = (after, lock) => {
    if (session.me?.student?.ms) { after?.(); return; }
    // (asked twice while the chunk comes: the second finds the first open)
    const go = () => { if (Login && !overlays.some((o) => o.component === Login && !o.closing)) open(Login, { after, why: after ? 'go' : 'other', lock }); };
    if (Login) go(); else void loginSheet().then(go, offline);
  };
  const pcSheet = () => import('./screens/sheets/PcSheet.svelte');
  sheets.ask = (q) => new Promise((done) => { void askSheet().then((Ask) => open(Ask, { ...q, done }), () => { offline(); done(false); }); });
  sheets.askText = ({ placeholder, max, tel, value, line, ...q }) => new Promise((done) => {
    void askSheet().then((Ask) => open(Ask, { ...q, input: { placeholder, max, tel, value, line }, done: (yes: boolean, text: string) => done(yes ? text : null) }), () => { offline(); done(null); });
  });
  sheets.deepLink = (p) => deepLink(p);
  // the iPhone app already open: a tapped notification's "start" arrives as kb:open (ios/, its launch: ?startapp)
  $effect(() => {
    const open = (e: Event) => { const p = (e as CustomEvent<unknown>).detail; if (typeof p === 'string' && p) deepLink(p); };
    addEventListener('kb:open', open);
    return () => removeEventListener('kb:open', open);
  });
  // a new conversation opens with the keyboard up, as every AI app does. iOS raises it only for a focus inside the tap,
  // and the chunk may come later: a stand-in field takes the focus now, the assistant's own field takes it over as it
  // mounts (iOS keeps the keyboard across the move) with any words typed meanwhile; a reopened conversation keeps the
  // keyboard down to read it. The stand-in goes as it loses the focus, or soon after a failed load.
  const assistant = () => import('./screens/assistant/Assistant.svelte');
  sheets.assistant = (ctx) => asStudent(() => {
    // the keyboard stays down on opening (owner's recordings, Nov 17: the sheet settled in three jumps as the keyboard
    // squeezed it, twice); the greeting and the ready questions show whole, a tap on the field raises it. `fresh(ctx) &&`
    // brings the old way back
    const opener = document.activeElement as HTMLElement | null, focus = false && fresh(ctx);
    const keyboard = focus && onIos ? standIn() : null;
    void lazy(assistant, { ctx, focus, keyboard, opener }, 'sheet.assistant', ctx ? `${ctx.kind}:${ctx.id}` : '').then(() => setTimeout(() => keyboard?.remove(), 600));
  });
  function standIn(): HTMLInputElement {
    const f = document.createElement('input');
    f.tabIndex = -1; f.maxLength = 300; f.autocomplete = 'off'; f.setAttribute('aria-hidden', 'true');
    f.style.cssText = 'position:fixed;top:0;left:-10000px;width:1px;height:1px;opacity:0;border:0;padding:0;pointer-events:none';
    f.style.fontSize = '16px'; // iOS zooms into a smaller one
    document.body.append(f);
    f.focus({ preventScroll: true });
    f.addEventListener('blur', () => f.remove(), { once: true });
    return f;
  }
  const rosterWelcome = () => import('./screens/sheets/RosterWelcome.svelte'), rosterAsk = () => import('./screens/sheets/RosterAsk.svelte');
  sheets.consent = () => { asked = true; void loadMe(); };
  let registryOpened = false; // in this launch, by any path: the desk's auto-open stays off after it (lib/desk.ts)
  sheets.registry = () => { registryOpened = true; return lazy(() => import('./screens/dmp/RegistrySheet.svelte'), {}); };
  sheets.celebrate = () => void celebrate();
  setLoginHook((after, lock) => sheets.login(after, lock));

  // ---- the Clubs tab: one feed for everyone; a club of mine opens its Studio pushed over it (round 5) ----
  // the bar's tabs: the forum only where the server opened it (FORUM_CHANNEL; its policy section in force)
  const tabs = $derived(TABS.filter((k) => k !== 'forum' || session.channel));
  $effect(() => { if (session.boardKnown && !session.channel && ui.tab === 'forum') ui.tab = 'afisha'; }); // the server's word, not the launch copy's
  $effect(() => {
    const uid = session.me?.id, blocked = session.banned || session.revoked;
    untrack(() => {
      resetResearch();
      if (uid && !blocked) { if (session.channel) void loadResearch(); void loadResearchRequests(); }
    });
  });
  const forumViewer = $derived(!session.banned && !session.revoked && session.boardKnown && session.channel ? session.me?.id : null);
  $effect(() => { if (forumViewer) return watchChannelVisit(); });
  // a role changes a tab's content, never its name
  const TAB_LABEL: Record<Tab, () => string> = { afisha: () => t('tab.afisha'), forum: () => t('tab.forum'), club: () => t('page.clubs'), profile: () => t('tab.profile') };
  const TAB_DOT: Record<Tab, () => boolean> = {
    afisha: () => (session.me?.counters.unreadBroadcasts ?? 0) > 0, forum: () => ui.tab !== 'forum' && channelUnread(), club: () => false,
    profile: () => (session.me?.counters.friendRequests ?? 0) > 0 || (session.me?.counters.inbox ?? 0) > 0,
  };
  // the iPhone app: its own tab bar in place of Nav's tabs, and my tickets kept for the door without a network (native.ts)
  $effect(() => { if (native.has('tabs')) nativeTabs(tabs.map((k) => ({ id: k, title: TAB_LABEL[k](), dot: TAB_DOT[k]() })), ui.tab, gated || !!session.banned || !!session.revoked, goTab); });
  $effect(() => { if (native.has('tickets') && data.eventsReady && !data.error) nativeTickets([...data.events, ...data.opened], i18n.lang); });
  /** A club of mine: the Clubs tab with its Studio pushed over it. */
  function toClub(org: number) { ui.tab = 'club'; sheets.studio(org); }
  // a screen builds on its first showing and stays alive (scroll kept); a tab never shown builds nothing (the hidden tabs
  // were ~1400 of 1900 nodes and 40 % of the blocking time at start)
  const built = $state<Record<string, boolean>>({});
  // (the Clubs tab waits for who I am: the copy or the server, a frame; else a member's hidden catalogue built too)
  $effect(() => { if (ui.tab === 'club' && !session.ready) return; if (!built[ui.tab]) built[ui.tab] = true; });
  // a built tab's chunk (offline: tried again on the next switch of tab)
  $effect(() => { void ui.tab; for (const k of TABS) if (built[k] && !pageReady(k)) loadPage(k).catch(() => {}); });
  // ...and once the start has settled, the rest are built one per idle moment, so the first tap on a tab only shows it
  // (a cold mount was the one long task left on a switch: ~1 s at 4x CPU). Away they cost nothing more: the hidden tab
  // is skipped by the engine (.tab below); their effects wait for ui.tab (loads, the badge's drop, the forum's seen line).
  // A tab built while away was never laid out or drawn: its first showing did all of it inside the tap (Profile: ~150 ms
  // at 4x CPU). So each one, once built, is drawn once in a later idle moment, unseen (.drawing), then skipped again with
  // its layout kept; the tap only shows it.
  let drawing = $state<string | null>(null);
  const idle = (fn: () => void) => { if ('requestIdleCallback' in window) requestIdleCallback(fn, { timeout: 4000 }); else setTimeout(fn, 500); };
  function prebuild() {
    const k = tabs.find((x) => !built[x] && (x !== 'club' || session.ready));
    if (session.banned) return;
    // the tabs are built: now the map, with MapLibre, its workers and the first floor (owner, Nov 15: the first tap on
    // the map opens it at once, no blank frame)
    if (!k) { idle(warmMap); return; }
    built[k] = true;
    const draw = () => idle(() => {
      if (ui.tab === k) { idle(prebuild); return; }
      drawing = k;
      requestAnimationFrame(() => setTimeout(() => { drawing = null; idle(prebuild); }));
    });
    // a tab in its own chunk is drawn unseen once the chunk is in (else the first tap would lay it out)
    if (pageReady(k)) draw(); else loadPage(k).then(draw, draw);
  }
  // a tab switched to: its time to the screen (the first one is the app's open time, below)
  let firstTab = true;
  $effect(() => {
    const k = ui.tab, at = performance.now();
    count(`tab.${k}`);
    if (firstTab) { firstTab = false; return; }
    untrack(() => loadPage(k)).then(() => timed(`tab.${k}`, at), () => {});
  });
  onFail.fn = (kind) => count(`api.${here()}.${kind}`);
  addEventListener('error', (e) => crashed(here(), e.error ?? e.message));
  addEventListener('unhandledrejection', (e) => crashed(here(), e.reason));
  // the app's open time ends at the first frame drawn with the first tab built and something to show (the copy or the server)
  let measured = false;
  $effect(() => { if (measured || !built[ui.tab] || !pageReady(ui.tab) || !session.ready || !data.eventsReady) return; measured = true; requestAnimationFrame(() => setTimeout(painted)); });
  // the capsule says what the top overlay is (SPEC §8.2); a closing one lets go at once, so it morphs back with the exit.
  // It takes that overlay's own theme too (the map's switch), so it never sits light on a dark map.
  // The top overlay that speaks decides (a Pane at rest is quiet but still the top: the capsule never names the page
  // under it); a menu or an Ask says nothing and lets the one below speak.
  const capOf = $derived([...overlays].reverse().find((o) => !o.closing && (o.title || o.quiet)));
  // over the Feed the capsule turns into tinted dark glass (chrome.ts); a titled overlay over it (the map, a sheet) takes
  // the normal chrome (owner's video, Oct 25: the map's capsule kept the Feed's tint)
  $effect(() => { feedChrome(capOf?.feed ? 1 : 0, 'opacity 220ms ease'); });
  // a full-screen overlay on top (the map): no capsule of ours over it (owner, Nov 26); it lets go at once on closing
  const bare = $derived(!![...overlays].reverse().find((o) => !o.closing)?.bare);

  // ---- live capsule: an event today you're going to, or a class within the next hour ----
  let clock = $state(nowTs());
  // the anthem playing in the background (its sheet's small button): the time left, a tap opens the sheet again
  const anthemLive = $derived.by<Live | null>(() => {
    if (!anthem.bg) return null;
    const left = Math.max(0, Math.floor(anthem.dur) - Math.floor(anthem.cur));
    return { kind: 'class', title: t('anthem.title'), at: 0, emoji: 'headphone_3d', tint: 'var(--accent)', label: `−${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`, onopen: () => sheets.anthem() };
  });
  const live = $derived.by<Live | null>(() => {
    const now = clock;
    const running = runningCheckin(now); // wins over a class or an event while it runs
    if (running) return { kind: 'checkin', title: running.title, at: now, emoji: 'laptop_3d', tint: 'var(--accent)', label: t('cap.checkin'), onopen: () => openCheckin(running) };
    if (anthemLive) return anthemLive;
    const today = dayNo(now);
    const ev = data.events.find((e) => e.my?.status === 'going' && e.status !== 'cancelled' && dayNo(e.startsAt) === today && (e.endsAt ?? e.startsAt + 3 * 3600) > now
      && (e.endsAt ?? e.startsAt) - e.startsAt < 86400); // not one of several days (a casting over a week: owner, Nov 3)
    // my club hosts (or co-hosts) it: an hour before till the end, its card with the team's tools (scanner: EventSheet) (owner, Nov 15)
    const mine = new Set(session.me?.memberships.map((x) => x.org.id));
    const host = data.events.find((e) => e.status !== 'cancelled' && (mine.has(e.org.id) || (!!e.coHost && mine.has(e.coHost.id)))
      && e.startsAt - 3600 <= now && (e.endsAt ?? e.startsAt + 3 * 3600) > now && (e.endsAt ?? e.startsAt) - e.startsAt < 86400);
    if (host) {
      const mins = Math.ceil((host.startsAt - now) / 60);
      return { kind: 'event', title: host.title, at: host.startsAt, emoji: host.emoji ?? host.org.emoji, tint: host.tint,
        label: mins > 0 ? t('cap.inMin', { n: mins }) : host.endsAt ? t('cap.until', { time: time(host.endsAt) }) : time(host.startsAt),
        onopen: () => sheets.event(host.id) };
    }
    const cls = classesLeft(data.schedule, now).find((x) => x.b - now <= 3600 && !skipped.has(classKey(today, x.c)));
    if (cls) {
      const mins = Math.ceil((cls.b - now) / 60);
      return { kind: 'class', title: subjectOf(cls.c) + (cls.c.room ? ' · ' + cls.c.room : ''), at: cls.b, emoji: classEmoji(cls.c), tint: '#2FBF71',
        label: mins > 0 ? t('cap.inMin', { n: mins }) : t('cap.until', { time: cls.c.ends }), onopen: () => { ui.tab = 'afisha'; } };
    }
    if (ev) return { kind: 'event', title: ev.title, at: ev.startsAt, emoji: ev.emoji ?? ev.org.emoji, tint: ev.tint, label: time(ev.startsAt), onopen: () => sheets.ticket(ev.id) };
    return null;
  });

  // the capsule is always there and always says where you are and what's happening (owner, Oct 30: never an empty pill,
  // it answers every tap): the busy word, else the top overlay's name, else the tab's (the live status wins on a tab)
  // the live status takes the capsule only once the person rests: a tap or a tab switch brings the tab's name back
  // (owner, Nov 9: it never answered the tabs)
  // 2.5 s after the finger lifts (owner, Nov 11: 5 s felt slow): time to read the tab's name, no longer; never while
  // a finger is down (a long scroll)
  let resting = $state(false), restTimer: ReturnType<typeof setTimeout>;
  const REST_MS = 2500;
  // a tap on the capsule itself is not activity: it would swap the live status for the tab's name under the finger
  // and the tap would open nothing (owner, Nov 11)
  const poke = (e: Event) => { if ((e.target as Element | null)?.closest?.('.cap-theme')) return; resting = false; clearTimeout(restTimer); };
  const rest = () => { clearTimeout(restTimer); restTimer = setTimeout(() => (resting = true), REST_MS); };
  $effect(() => {
    rest();
    const o = { capture: true, passive: true };
    // touchend, not pointercancel: a touch scroll cancels the pointer as it starts, the finger still down
    const ends = ['pointerup', 'touchend', 'touchcancel'];
    addEventListener('pointerdown', poke, o); for (const e of ends) addEventListener(e, rest, o);
    return () => { removeEventListener('pointerdown', poke, o); for (const e of ends) removeEventListener(e, rest, o); clearTimeout(restTimer); };
  });
  // the capsule holds a check-in from /me alone: finished or taken away elsewhere, only asking again lets it go
  const holdingCheckin = $derived(!!session.me?.checkin);
  $effect(() => {
    if (!holdingCheckin) return;
    const id = setInterval(() => { if (!document.hidden) void loadMe(true); }, 60_000);
    return () => clearInterval(id);
  });
  const capTitle = $derived(ui.busy || (capOf ? (capOf.mark ? null : capOf.title) : live && (resting || live.kind === 'checkin') ? null : TAB_LABEL[ui.tab]()) || null);
  // a spinner while a tap's work runs; a view that forgot its own icon gets the app's mark (Sparkles is the assistant's alone)
  const capIcon = $derived(ui.busy ? LoaderCircle : capOf ? (capOf.icon ?? KbtuMark) : TAB_ICON[ui.tab]);

  // ---- Back button: closes the top overlay ----
  const showBack = $derived(!session.banned && !session.revoked && ((!gated && overlays.some((o) => !o.closing && !o.holdBack)) || !!backTo.fn));
  $effect(() => { if (showBack) backButton.show(); else backButton.hide(); });
  $effect(() => {
    if (!session.banned && !session.revoked) return;
    untrack(() => {
      dropLazy(); overlays.splice(0); backTo.fn = null;
      data.support = null; data.sponsors = null; data.donations = null;
    });
  });

  // ---- the clubs' rosters (PLAN 95): joined from DMP's list (a toast each, once), the welcome before the KBTU sign-in,
  // a row under another name; each sheet once per launch, after the start's own moments ----
  const rosterShown = new Set<string>();
  $effect(() => {
    const r = session.me?.roster;
    if (!booted || !r) return;
    untrack(() => {
      if (r.joined?.length) {
        r.joined.forEach((j, i) => setTimeout(() => { haptic.ok(); say(j.title ? t('ro.joined', { org: nameOf(j.org), title: j.title }) : t('ro.joinedPlain', { org: nameOf(j.org) }), 'party_popper_3d'); }, 600 + i * 2200));
        void api.rosterSeen().catch(() => {});
        if (session.me) session.me.roster = { ...r, joined: [] };
      }
      const key = r.welcome?.length ? 'welcome' : r.ask?.length ? `ask:${r.ask[0].id}` : '';
      if (!key || rosterShown.has(key)) return;
      rosterShown.add(key);
      // a launch moment: after whatever the start shows (the computer hint, ...) and after the policy gate, once nothing else is open
      moment(() => (r.welcome?.length ? lazy(rosterWelcome, { spots: r.welcome }) : lazy(rosterAsk, { row: r.ask![0] })));
    });
  });

  // ---- greeting ----
  opened(nowTs()); // every launch counts for "welcome back", a deep link's too
  idle(() => visit(dayNo(nowTs()))); // and for the one-time help ask (lib/helpus: this phone's days, kept on it), after the first paint
  // an office's own people (DMP) are greeted as the team, once per phone, full screen (owner, Nov 17: the toast was missed):
  // at the link that let them in (at once, then the link's own sheet), or as the launch's first moment after
  const officeWelcome = () => import('./screens/sheets/OfficeWelcome.svelte');
  // seen once it mounts; a chunk that fails to load still runs the link's own step (Codex review, Nov 17)
  // DMP's list (me.dmpHi): the same hello, remembered on the server once they leave it (its button: Microsoft).
  // From greet it is that moment itself (its promise holds the queue): ahead of the install offer on a first open
  // Left here once but the server never heard it (offline): not again on this phone, and it's told again
  function teamHi(then?: () => void): Promise<unknown> | false {
    const d = session.me?.dmpHi, o = d ?? session.me?.memberships.find((m) => m.org.kind === 'office')?.org ?? session.me?.office, key = 'kb-hi2-o' + o?.id;
    const left = 'kb-dmp-left' + session.me?.id;
    if (d && seen(left)) { void api.dmpHi().catch(() => {}); return false; }
    if (!o || !d && seen(key)) return false;
    const done = d ? () => { once(left); void api.dmpHi().catch(() => {}); if (session.me) session.me.dmpHi = null; then?.(); } : then;
    return officeWelcome().then((m) => open(m.default, { org: o, ondone: done, shown: () => once(key) }), () => then?.());
  }
  function greet() {
    const team = teamHi();
    if (team) return team;
    const now = nowTs(), first = session.me?.student?.firstName;
    const slots = classesLeft(data.schedule, now).filter((x) => !skipped.has(classKey(dayNo(now), x.c)));
    const next = nextUp(now, slots, data.events, (c) => subjectOf(c) + (c.room ? ' · ' + c.room : ''), classEmoji);
    const hi = hiNow(now, first ? ', ' + first : '', next, time);
    if (hi) say(phrase(hi.key, hi.vars), hi.emoji);
  }

  // ---- deep links: ev_<id> (event), tk_<id> (my ticket), cl_<id> (club), jr_<id> (a club's applications), mg_<id> (an event's organizer screen),
  // u_<id>_<code> (a profile: the QR on someone's badge; the code is for the door scanner),
  // friends (Profile with the Friends sheet: the bot's request message), donate, sponsors (Made together at its Support section) ----
  function deepLink(p = tg.startParam, afterSignIn = false) {
    if (p === 'vp') { void import('./screens/sheets/VpDiag.svelte').then((m) => open(m.default, {})); return; } // ponytail: the Android inset diagnostic
    if (p === 'donate') { ui.tab = 'profile'; sheets.settings(p); return; }
    if (p === 'sponsors') { ui.tab = 'profile'; sheets.credits('support'); return; }
    if (p === 'verify') { sheets.login(); return; }
    if (p === 'afisha') { ui.tab = 'afisha'; return; }
    if (p === 'map') { sheets.map(); return; }
    if (p === 'awards') { ui.tab = 'profile'; asStudent(() => sheets.awards()); return; }
    if (p === 'feed') { ui.tab = 'afisha'; sheets.feed(); return; }
    if (p === 'exit') { sheets.map(undefined, true); return; } // the owner's "help me get out" link (PLAN item 21)
    if (p === 'friends') { ui.tab = 'profile'; sheets.friends(); return; }
    if (p === 'me') { ui.tab = 'profile'; return; }
    if (p === 'apl') { ui.tab = session.channel ? 'forum' : 'profile'; if (session.me?.appeals) sheets.appeals(); return; } // the bot: SG answered my appeal   // the bot: "keep my account"
    if (p === 'ask') { ui.tab = 'profile'; if (session.me?.ask) sheets.askHuman(); return; } // the bot: my question to a person has an answer (old messages)
    if (p === 'cm') return; // the bot's "register" under a deleted Telegram comment: the comment's card is a launch moment (tgComment)
    if (p === 'lib') { ui.tab = 'profile'; if (session.me?.library) sheets.library(); return; } // the bot: my seat (a report, time running out) or the one I reported
    if (p === 'anthem') { sheets.anthem(); return; } // the volunteers' chat link: the anthem over the tab as it is, guests too
    if (p === 'android') { void lazy(() => import('./screens/sheets/AndroidTestSheet.svelte'), {}); return; } // the bot's android_test broadcast: become a tester of the app on Google Play
    if (p === 'capps') { sheets.admin(); return; }                              // the bot: a club to check
    if (p === 'achats') { sheets.adminChats(); return; }                        // the bot: suggested chats to check
    if (p === 'voices') { sheets.adminVoices(); return; }                       // the bot, to the creator: a line or an offer to help came
    if (p === 'newclub') { asStudent(() => sheets.createClub()); return; }      // the bot: my application's answer
    if (p === 'news') { ui.tab = 'afisha'; sheets.news(); return; } // every post: Afisha's "All"
    if (p === 'research') { if (session.channel) ui.tab = 'forum'; sheets.research(); return; }
    if (p === 'sched') {
      asStudent(() => {
        const schedule = loadSchedule(true);
        if (data.scheduleReady || data.schedule.length) void sheets.week();
        else void schedule.then(() => sheets.week());
      }, p);
      return;
    }
    if (p === 'rq') { asStudent(() => sheets.rosterRequests()); return; } // the bot: someone says they're in our DMP list
    if (p === 'people') { // the bot's "shall we name you?": Made together, and my answer's sheet over it while something there is mine
      ui.tab = 'profile';
      void Promise.all([loadCredits(), lazy(chunks.people, {})]).then(() => { if (data.credits?.mine) sheets.creditAsk(); });
      return;
    }
    if (p === 'clubs') { ui.tab = 'club'; return; } // the bot's "other clubs recruit now"
    if (p === 'chats') { // the bot's "your suggested chat is in the app": the chats directory
      ui.tab = 'club';
      void api.chats().then((c) => { data.chats = c; sheets.chats(c.all); }).catch(() => {});
      return;
    }
    // <prefix>_<arg>: one table (lib/state/openers.ts); a link the app doesn't know (cut, mistyped, or from something
    // since gone): said, not silently dropped (owner, Oct 30)
    if (!openDeepLink(p, { join: joinByLink, president: presidentByLink, msBack, checkIn, helpRun, takeDoor }, afterSignIn) && p) say(t('link.unknown'), 'thinking_face_3d');
  }

  // the app was closed while away at Microsoft (the page returns to plain Telegram): someone new types the student ID
  // now, then what the guest wanted before signing in runs
  // A scan of the big screen's QR: the server keeps it at once; a guest signs in (the sheet comes back to Telegram by
  // itself) and the same scan again shows it counted (the server counted it at the sign-up already)
  // The answer in the middle of the screen, not a toast (owner, Nov 10: guests at the door couldn't tell they were in)
  const ciResult = (props: { kind: CiKind; title: string; event?: number | null; onsign?: () => void; text?: string }) =>
    lazy(() => import('./screens/sheets/CheckinResult.svelte'), props);
  async function checkIn(p: string, again = false): Promise<void> {
    try {
      const r = await api.qrCheckin(p);
      count('do.qr');
      const kind = r.done ? (r.left ? 'left' : r.again ? 'again' : 'done') : session.me?.student || r.already || r.flagged ? 'no' : 'wait'; // no: the event didn't take it (window, members only)
      if (kind === 'wait' && again) return;
      const text = r.team && !r.left ? t('ci.team') : r.already ? t('ci.already', { time: time(r.already) }) : r.flagged ? t('ci.flagged') : undefined; // a ticket used already, a receipt to check: the scanner
      void ciResult({ kind, title: r.title, event: r.event ?? null, text, onsign: () => asStudent(() => void checkIn(p, true), p, true) });
      // my data starts going into the clubs' reports here: their consent asked once, after the answer has settled (CheckinResult's 2.6 s)
      if (r.team && r.done && !r.left) setTimeout(askAfterTeamMark, 2800);
    } catch (e) {
      const own = e instanceof ApiErr && e.message === 'own';
      const early = e instanceof ApiErr && e.message === 'not_open' && typeof e.data.at === 'number' ? t('ci.notOpen', { time: time(e.data.at as number) }) : undefined; // a guest before the door
      void ciResult({ kind: !(e instanceof ApiErr) ? 'error' : own || early ? 'no' : e.code === 'closed' ? 'closed' : e.message === 'qr_old' ? 'old' : e.message === 'qr_not_in' ? 'notIn' : 'error', title: '', text: own ? t('ci.own') : early });
    }
  }

  async function takeDoor(token: string): Promise<void> {
    try { const s = await api.volTake(token); haptic.ok(); sheets.screens(undefined, undefined, s); }
    catch (e) {
      haptic.error();
      say(t(!(e instanceof ApiErr) ? 'common.error' : e.message === 'member' ? 'ledg.handNotMember' : e.code === 'not_found' || e.code === 'conflict' ? 'ledg.handDead' : 'common.error'), 'pleading_face_3d');
    }
  }

  // An organizer's helper QR: the event named first, then its QR on this phone. The way back after closing it: the capsule
  async function helpRun(p: string): Promise<void> {
    try {
      let h = await api.qrHelper(p);
      if (!h.joined) {
        if (!(await sheets.ask({ title: t('scr.helpAsk', { title: h.title }), text: t('scr.helpText'), ok: t('scr.helpYes'), cancel: t('scr.keep') }))) return;
        h = await api.qrHelper(p, true);
        void loadMe(true); // the capsule: my way back to this QR
      }
      haptic.ok();
      sheets.helperQr(h.session, h.event, h.scanner);
    } catch (e) {
      haptic.error();
      say(!(e instanceof ApiErr) ? t('common.error') : e.code === 'closed' ? t('ci.closed') : e.message === 'qr' || e.message === 'qr_old' ? t('scr.helpOld') : t('common.error'), 'pleading_face_3d');
    }
  }

  // force: the Microsoft return's own call (its start param is ms_, nothing else to open)
  function msBack(force = false) {
    if (!inTelegram) return;
    // go_<id>: a guest's "I'm going" from before the sign-in, kept on the phone only (never a start param: a shared link
    // must not sign anyone up)
    const again = () => {
      const p = takeAgain(), go = p?.match(/^go_(\d+)$/);
      if (!go) { if (p) deepLink(p, true); return; }
      const id = Number(go[1]), st = eventById(id)?.my?.status;
      sheets.event(id);
      if (st !== 'going' && st !== 'hold' && st !== 'waitlist') toggleGoing(id, () => sheets.pay(id));
    };
    if (session.me?.msPending) sheets.login(again);
    else if (session.me?.student && (force || !tg.startParam)) again();
  }

  // the copy for the next launch follows what the screens show, a second after it settles (only once the server answered).
  // The effect reads only the lists' references and data.kept (a tap's change inside a list): no deep read before the
  // paint; the JSON is made when the app is idle, and again as it goes to the background.
  // ponytail: a change deep inside a list that bumps no data.kept waits for the next reload or the background; bump it there if one matters
  const snap = () => ({ me: session.me, events: data.events, orgs: data.orgs, schedule: data.schedule, posts: data.posts, castings: data.castings, gallery: data.gallery.filter((p) => !p.pending).slice(0, 4), galleryAlbums: data.galleryAlbums.slice(0, 4), galleryPost: data.galleryPost, friends: data.friends, myCard: data.myCard, news: data.news, studio: data.studio, team: data.team });
  const keepable = () => booted && session.verified && !data.error && !session.failed && !session.banned;
  let keepTimer: ReturnType<typeof setTimeout> | undefined;
  // no $state.snapshot: a clone through the proxies cost more. A part whose list is the same object as last time (and no
  // data.kept since) reuses its JSON: a tab's own refresh (friends, my card) re-wrote all 400 events, 60 ms through the
  // proxies on each visit. Going to the background writes everything afresh (`all`): it catches the ponytail case above.
  const jsonOf = new Map<string, { ref: unknown; kept: number; json: string }>();
  const keep = (all = false) => {
    if (!keepable()) return;
    const out: string[] = [];
    for (const [k, v] of Object.entries(snap())) {
      const m = jsonOf.get(k);
      // (studio and team are records of lists that gain a key in place: always written; they are small)
      const json = !all && m && m.ref === v && m.kept === data.kept && k !== 'studio' && k !== 'team' ? m.json : JSON.stringify(v);
      if (json === undefined) continue; // as JSON.stringify of the whole drops an undefined field
      jsonOf.set(k, { ref: v, kept: data.kept, json });
      out.push(`${JSON.stringify(k)}:${json}`);
    }
    writeCache(`{${out.join(',')}}`);
    void keepTickets(data.events, !data.offline); // the door's copy: outlives the snapshot's week (lib/offlineTickets)
  };
  $effect(() => {
    void [data.kept, ...Object.values(snap()), ...Object.values(data.studio), ...Object.values(data.team)]; // a club's list loaded: a new key
    if (!keepable()) return;
    clearTimeout(keepTimer);
    keepTimer = setTimeout(() => ('requestIdleCallback' in window ? requestIdleCallback(() => keep(), { timeout: 3000 }) : keep()), 1000);
  });
  onMount(() => {
    const away = () => { if (document.hidden) { clearTimeout(keepTimer); keep(true); } };
    document.addEventListener('visibilitychange', away);
    // back after 30 s or more: the app's data again, quietly (every loader keeps its last copy if it fails). Telegram's
    // events and the page's both land here; the first one back clears leftAt, so one return is one refresh. Not the Gallery:
    // its first page would cut the list of a viewer left open, and it reloads as it opens.
    let leftAt = 0;
    const left = () => { leftAt ||= Date.now(); };
    const back = () => {
      if (leftAt && Date.now() - leftAt >= 30_000) {
        void loadMe(true); void loadAfisha(); loadMine(); void loadInbox(); void loadCredits();
        if (session.channel || data.research) void loadResearch();
        void loadResearchRequests();
      }
      leftAt = 0;
    };
    const seen = () => (document.hidden ? left() : back());
    document.addEventListener('visibilitychange', seen);
    const offs = [on('deactivated', left), on('activated', back)];
    // the network gone: the kept tickets at once; back: the lists and the account again (the offline note goes with the answer)
    const offline = () => { data.offline = true; };
    const online = () => { if (data.offline) { void loadMe(true); void loadAfisha(); } };
    addEventListener('offline', offline);
    addEventListener('online', online);
    return () => { document.removeEventListener('visibilitychange', away); document.removeEventListener('visibilitychange', seen); removeEventListener('offline', offline); removeEventListener('online', online); offs.forEach((f) => f()); };
  });

  // The API and cache already translate the first load. Walk the reactive stores only when the language changes.
  let localizedLang = untrack(() => i18n.lang);
  $effect(() => {
    const lang = i18n.lang;
    if (lang === localizedLang) return;
    localizedLang = lang;
    untrack(() => { localize(data); localize(session.me); });
  });

  // ---- a new achievement level the app hasn't celebrated yet (§4.11): one moment at a time, once the app has settled ----
  // (and after signing in later: a returning student may bring one)
  let booted = $state(false), wasStudent = false;
  $effect(() => {
    const st = !!session.me?.student;
    if (st !== wasStudent) untrack(() => {
      // known to be a student (the stored copy, the server, a sign-in): Profile's and the club tab's pages fill at once
      loadMine();
      void loadGallery();
      void loadInbox(true); // staff only (it checks)
    });
    if (st && !wasStudent && booted) { moment(tgComment); moment(celebrate); } // signed in just now: his comment first
    wasStudent = st;
  });
  function loadMine() {
    if (session.me?.bigScreen || session.me?.memberships.some((m) => ['president', 'vice', 'head'].includes(m.role))) void loadMeetups();
    for (const m of session.me?.memberships ?? []) if (may(m, 'events') || m.role === 'head') void loadMeetupSetup(m.org.id);
    void loadFriends(); void loadMyCard(true); void loadNews(true); // StoryRow's refresh at the same launch joins it
    const club = session.me?.memberships.find((m) => m.org.id === ui.club) ?? session.me?.memberships[0];
    if (club) { void loadStudio(club.org.id); void loadTeam(club.org.id); }
    if (session.me?.oversee) void loadRegistry();
    if (session.me?.vol?.ledger) void loadVol();
    if (session.me?.appeals) void loadAppeals();
    if (session.me?.library) void loadLibrary();
    if (session.me?.appeals?.sg) void loadSg();
    if (session.me?.ask) void loadAsks();
    if (session.me?.ask?.staff) void loadHelpq();
  }

  function warmNavigation() {
    if (session.banned || session.revoked) return;
    void loginSheet().catch(() => {}); void askSheet().catch(() => {});
    warm(chunks.person); warm(chunks.club);
    if (inTelegram && session.me && !session.me.canDm) warm(dmSheet);
    for (const tab of tabs) void loadPage(tab).catch(() => {});
  }
  // my own comment the bot deleted in the forum channel's Telegram group (the server knows me by the signed initData,
  // not by the bot's button, startapp=cm): the first launch moment, the others wait behind it (owner, Nov 1)
  async function tgComment() {
    if (!session.tgComment) return;
    session.tgComment = false;
    const c = await api.tgComment().catch(() => null);
    if (c) return lazy(() => import('./screens/sheets/TgCommentSheet.svelte'), { c });
  }
  // each level is one launch moment; "First 500" isn't one: it's the lanyard's drop on the first Profile open (Hero)
  async function celebrate() {
    const me = session.me, next = me?.unlocked?.find((x) => x.code !== 'first50');
    if (!me || !next) return;
    const done = () => api.markUnlocked(next.code, next.level).then((r) => { if (session.me) session.me = { ...session.me, unlocked: r.unlocked }; moment(celebrate); }).catch(() => {});
    const a = (await api.person(me.id).catch(() => null))?.awards.achievements.find((x) => x.code === next.code && x.level > 0);
    if (!a) { void done(); return; }
    const m = await import('./screens/sheets/Unlock.svelte');
    open(m.default, { a, ondone: done });
  }

  function joinByLink(org: number, token: string) {
    const club = data.orgs.find((x) => x.id === org)?.name ?? '';
    asStudent(async () => {
      // already in it (my own club's link, shared or opened again): nothing to join
      const mine = session.me?.memberships.find((m) => m.org.id === org);
      if (mine) { say(t('join.already', { club: mine.org.name }), 'raising_hands_3d_default'); sheets.club(org); return; }
      if (!(await sheets.ask({ title: t('join.linkAsk', { club }), text: t('join.linkText'), ok: t('join.linkOk'), cancel: t('common.cancel') }))) return;
      try {
        const o = await api.acceptInvite(token);
        await loadMe(); studioChanged();
        haptic.ok(); if (!teamHi(() => sheets.club(o.id))) { say(t('join.linkDone', { club: o.name }), 'party_popper_3d'); sheets.club(o.id); }
      } catch { haptic.error(); say(t('join.linkDead'), 'pleading_face_3d'); sheets.club(org); } // used or old: the club, to apply there
    });
  }

  /** The admin's one-time President link: asked first; then the club is mine to lead, and Studio opens on it. */
  function presidentByLink(org: number, token: string) {
    const club = data.orgs.find((x) => x.id === org)?.name ?? '';
    asStudent(async () => {
      if (!(await sheets.ask({ title: t('pres.ask', { club }), text: t('pres.text'), ok: t('pres.ok'), cancel: t('common.cancel') }))) return;
      try {
        const o = await api.acceptInvite(token);
        await loadMe(); studioChanged();
        haptic.ok(); burst(); if (!teamHi(() => toClub(o.id))) { say(t('pres.done', { club: o.name }), 'party_popper_3d'); toClub(o.id); }
      } catch { haptic.error(); say(t('join.linkDead'), 'pleading_face_3d'); }
    });
  }

  // a computer: a sheet that the app is made for phones, with a code for the phone, until "continue on the computer"
  // (never forbid; warn properly, not a toast)
  function computerHint() {
    try { if (!onComputer || localStorage.getItem('kb-pc2')) return; } catch { return; }
    return lazy(pcSheet, { ok: () => { try { localStorage.setItem('kb-pc2', '1'); } catch { /* blocked: it asks again next time */ } } });
  }

  // the home-screen app, offered once per phone (InstallSheet marks it shown): phones in Telegram only, (for everyone later) never on this
  // phone's first launch (the welcome, the sign-in and the policy come first) nor on a launch that came for something
  // (a deep link); the last of the launch's moments
  let hinted = false;
  // the bot can't write to them (they never opened its chat): on every launch until it can (owner, Nov 23: ~half the
  // users get no tickets or reminders); Telegram's own "allow messages" is one tap
  // a sheet that shows it (DmSheet: a plain question was closed unread), its chunk warmed with the first sheets
  const dmSheet = () => import('./screens/sheets/DmSheet.svelte');
  let dmHinted = false;
  function dmHint() {
    if (dmHinted || !session.me || session.me.canDm || session.banned || session.revoked) return;
    dmHinted = true;
    return lazy(dmSheet, {});
  }
  function installHint() {
    if (hinted) return;
    if (!inTelegram || onComputer || tg.startParam || seen('kb-install')) return;
    hinted = true;
    return lazy(() => import('./screens/sheets/InstallSheet.svelte'), {});
  }

  onMount(() => {
    // Drop old navigation checkpoints, including per-copy keys in both sign-in modes.
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key && /^(?:kb-nav(?::\d+)?|kb-(?:web-)?recovery:\d+:[^:]*:kb-nav:[^:]*)$/.test(key)) localStorage.removeItem(key);
      }
    } catch { /* storage blocked */ }
    count(launchedFrom(tg.startParam));
    const offBack = backButton.onClick(() => { if (!overlays.some((o) => !o.closing) && backTo.fn) backTo.fn(); else close(); });
    // a keyboard's Esc does what Telegram's Back does (Telegram Desktop, a plain browser)
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && !gated && overlays.some((o) => !o.closing)) close(); };
    addEventListener('keydown', esc);
    // the last copy first (the instant re-open), the server's answer replaces it
    const snap = readCache(inTelegram ? tg.user?.id : session.me?.tg.id);
    if (snap) {
      localize(snap); // translate the plain cache before assigning it to reactive state
      if (inTelegram) {
        session.me = snap.me; session.ready = true; session.board = !!snap.me?.board; session.channel = !!snap.me?.forumChannel; // the last launch's word until the server's
      }
      data.events = snap.events; data.orgs = snap.orgs; data.schedule = snap.schedule; data.posts = snap.posts; data.castings = snap.castings ?? []; data.friends = snap.friends ?? null; data.myCard = snap.myCard ?? null; data.news = snap.news ?? null; data.studio = snap.studio ?? {}; data.team = snap.team ?? {}; data.eventsReady = true;
      data.scheduleReady = !!snap.schedule.length; data.postsReady = !!snap.posts.length;
      data.gallery = snap.gallery ?? [];
      data.galleryAlbums = snap.galleryAlbums ?? [];
      data.galleryPost = snap.galleryPost ?? null; // the Gallery's Add from the start (its grid takes it as it opens)
      setTimeout(() => moment(installHint)); // the last launch's word is enough to decide: at once, not after the server
    }
    const account = inTelegram ? loadMe(false, true) : Promise.resolve();
    const afisha = loadAfisha();
    // Warm the first event while the lists are on their way.
    warm(chunks.event);
    void account.then(() => {
      // Made together: Profile's row and its screen, ahead of any tap. Something of mine there and never answered:
      // the "show your name?" sheet once on this phone (owner, Nov 20: few open that screen, so ask at the door)
      const credits = loadCredits();
      if (session.banned || session.revoked) return;
      void loadSupport();
      requestAnimationFrame(() => setTimeout(warmNavigation));
      // A Microsoft return without a start parameter can still carry a verified pending claim.
      const microsoftReturn = !!session.me?.msPending;
      if (inTelegram && !tg.startParam && session.me && !session.me.student?.ms && !microsoftReturn) {
        void api.msClaim('').then(async () => {
          await loadMe();
          if (session.banned || session.revoked) return;
          haptic.ok();
          if (session.me?.student?.ms) say(t('login.msDone'), 'sparkles_3d');
          msBack(true);
        }, () => {});
      }
      if (!tg.startParam && !microsoftReturn && !gated && !session.tgComment && !overlays.length) {
        // The greeting names the next class or event, so it still waits for the agenda.
        void afisha.then(() => { if (!session.banned && !session.revoked) moment(greet); });
      }
      if (tg.startParam) deepLink();
      else if (session.me?.msPending) msBack();
      void credits.then(() => {
        const v = data.credits?.version, k = `cr.asked.${v}`;
        if (data.credits?.mine?.consent !== null || data.credits?.mine == null || ui.gate) return;
        try { if (localStorage.getItem(k)) return; localStorage.setItem(k, '1'); } catch { return; }
        moment(() => sheets.creditAsk());
      });
      // the owner: Android people are offered the Google Play closed test on entry (no broadcast), once more 3 days on
      // if they closed it (lib/androidTest.ts); never once they've opened the installed app. Profile's row stays.
      if (onAndroid && inTelegram && !ui.gate && !session.me?.androidApp) {
        const due = offerDue();
        if (due === 'again') count('andr.again');
        if (due) moment(() => void lazy(() => import('./screens/sheets/AndroidTestSheet.svelte'), {}));
      }
      setTimeout(chunks.ticket, 1500); setTimeout(warmPages, 3000); setTimeout(warmChannel, 1800); setTimeout(warmSubjects, 3500); setTimeout(prebuild, 2500);
      if (!inTelegram && session.me && !session.me.student?.ms) sheets.login();
      // the launch's own moments, in this order, one at a time once the screen is free; the roster's queue up as it comes
      // DMP at a computer: its registry, wide, instead of the phone hint (once per launch; Back leaves it for the app)
      const desk = deskRegistry(session.me?.oversee, tg.startParam, inTelegram && onComputer);
      // asked again when its turn comes: opened by hand meanwhile (a slow start), it stays as the person left it
      if (inTelegram) { moment(tgComment); moment(desk ? () => { if (deskRegistry(session.me?.oversee, tg.startParam, inTelegram && onComputer, registryOpened)) sheets.registry(); } : computerHint); }
      booted = true; setTimeout(() => { moment(celebrate); moment(installHint); moment(dmHint); });
    });
    const clockTimer = setInterval(() => (clock = nowTs()), 30000);

    return () => {
      offBack();
      clearInterval(clockTimer);
      removeEventListener('keydown', esc);
    };
  });
</script>

<main class="app">
  {#if session.revoked}
    <div class="banned" role="alert"><p>{t('common.error')}</p></div>
  {:else if !session.banned}
    {#each tabs as tab (tab)}
      <section class="tab" class:on={ui.tab === tab} class:drawing={drawing === tab && ui.tab !== tab} aria-hidden={ui.tab !== tab} inert={gated}>
        {#if tab === 'afisha'}
          {#if built.afisha}<ListPage />{/if}
        {:else}
          {@const Page = pages[tab]}
          {#if built[tab] && Page}<Page />{/if}
        {/if}
      </section>
    {/each}

    <!-- the feed's posters go full height (the top's fade is the tab's own mask, .tab below) -->
    <div class="botfade" aria-hidden="true" use:unfeed></div>
    <div class="tgfade" aria-hidden="true"></div>
    <div class="cap-theme {capOf?.theme ? `theme-${capOf.theme}` : ''}" class:bare><Capsule {live} title={capTitle} icon={capIcon} spin={!!ui.busy} mark={!ui.busy && !!capOf?.mark} tint={capOf?.tint} /></div>
    <Nav {tabs} labels={tabs.map((k) => TAB_LABEL[k]())} dot={tabs.map((k) => TAB_DOT[k]())} />
    {#if StandaloneBar && !gated}<StandaloneBar back={showBack} tint={capOf?.tint} />{/if}

    {#if gated}
      {#await consentGate() then m}<m.default oncancel={() => (asked = false)} />{/await}
    {:else}
      <!-- Keep exiting entries mounted until their animation calls removeOverlay. -->
      {#each overlays as o (o.id)}<o.component {...o.props} overlay={o} />{/each}
    {/if}
    <Toast />
  {/if}
  {#if session.banned}
    <div class="banned" role="alertdialog" aria-labelledby="ban-t">
      <span class="bico"><Ban size={34} /></span>
      <h2 id="ban-t" class="t-h2">{t('ban.title')}</h2>
      {#if session.banned.reason}<p class="t-callout">{t('ban.reason', { reason: session.banned.reason })}</p>{/if}
      {#if session.banned.contact}<button class="bapp" onclick={() => openLink('https://t.me/' + session.banned!.contact)}>{t('ban.appeal')}</button>{/if}
      <p class="t-foot">{t('ban.data')}</p>
    </div>
  {/if}
  <!-- a phone turned sideways in the home-screen app (iOS can't lock it; Telegram's Mini App is locked by Telegram) -->
  <div class="turn" aria-hidden="true"><Smartphone size={34} /><p class="t-callout">{t('app.turn')}</p></div>
</main>

<style>
  .cap-theme { display: contents; }
  .cap-theme.bare :global(.cap) { visibility: hidden; }
  .turn { display: none; }
  @media (orientation: landscape) and (max-height: 500px) {
    :global(html[data-web]) .turn { position: absolute; inset: 0; z-index: 10001; display: flex; flex-direction: column; align-items: center;
      justify-content: center; gap: 12px; background: var(--bg); color: var(--text-2); }
  }
  .banned { position: absolute; inset: 0; z-index: 10000; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px;
    padding: 24px; text-align: center; background: var(--glow), var(--bg); }
  .bico { width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger-text); }
  .banned p { max-width: 320px; color: var(--text-2); overflow-wrap: anywhere; }
  .bapp { margin-top: 8px; height: 44px; padding: 0 20px; border-radius: var(--r-full); background: var(--surface-2); font: 650 15px/1 var(--font-text); }
  /* and under the bottom bar, softer: the glass still has something to bend (mockup v23) */
  /* Telegram fullscreen only: Telegram draws its own dark scrim behind its buttons; our page-coloured fade over the page makes
     it read as ours. It ends with Telegram's row (--top: 0 outside fullscreen); the home-screen app has no such scrim (its
     --top is the bar's room, and this ran 60 px past the bar there) */
  .tgfade { position: absolute; top: 0; left: 0; right: 0; height: var(--top); z-index: calc(var(--z-capsule) - 1); pointer-events: none;
    background: linear-gradient(var(--bg), transparent); }
  :global(html[data-web]) .tgfade { display: none; }
  .botfade { position: absolute; inset: 0; z-index: calc(var(--z-nav) - 1); pointer-events: none; background: var(--bg);
    -webkit-mask-image: linear-gradient(0deg, rgba(0, 0, 0, 0.85), transparent calc(var(--bottom) + 40px));
    mask-image: linear-gradient(0deg, rgba(0, 0, 0, 0.85), transparent calc(var(--bottom) + 40px)); }
  /* clip, not just hidden: a hidden box can still be scrolled by code, and a sheet's scrollIntoView (the club's chats)
     scrolled the whole app 80 px up, the tab bar back into view over the sheet; hidden stays for older webviews */
  .app { position: absolute; inset: 0; overflow: hidden; overflow: clip; background: var(--bg); isolation: isolate; }
  /* one palette on every tab: a hue swap per tab looked childish; the lights wander wide instead of
     breathing in place ("they look sealed, they should float") */
  /* a tab away sits under the one shown (same box), so it never takes a tap: `pointer-events` is inherited, and
     flipping it restyled every node of the tab on each switch (the Forum: 1100 nodes, ~100 ms at 4x CPU) */
  .tab { position: absolute; inset: 0; visibility: hidden; z-index: -1;
    /* scrolled content fades out under the clock and Telegram's buttons instead of running into them: a mask on the tab,
       never a strip of --bg over it (that was a band over any other ground, and iOS < 16.2 dropped its colour mix).
       To 12% up there, the strip's old depth. Eased, not linear: a linear fade ends in a kink the eye reads as a hard
       line under the head (owner, Nov 23) */
    --a: var(--edge-from); --d: calc(var(--edge-to) - var(--a));
    -webkit-mask-image: linear-gradient(rgba(0, 0, 0, 0.12) var(--a), rgba(0, 0, 0, 0.19) calc(var(--a) + var(--d) * 0.1), rgba(0, 0, 0, 0.34) calc(var(--a) + var(--d) * 0.25),
      rgba(0, 0, 0, 0.56) calc(var(--a) + var(--d) * 0.42), rgba(0, 0, 0, 0.76) calc(var(--a) + var(--d) * 0.6), rgba(0, 0, 0, 0.91) calc(var(--a) + var(--d) * 0.78),
      rgba(0, 0, 0, 0.98) calc(var(--a) + var(--d) * 0.92), #000 var(--edge-to));
    mask-image: linear-gradient(rgba(0, 0, 0, 0.12) var(--a), rgba(0, 0, 0, 0.19) calc(var(--a) + var(--d) * 0.1), rgba(0, 0, 0, 0.34) calc(var(--a) + var(--d) * 0.25),
      rgba(0, 0, 0, 0.56) calc(var(--a) + var(--d) * 0.42), rgba(0, 0, 0, 0.76) calc(var(--a) + var(--d) * 0.6), rgba(0, 0, 0, 0.91) calc(var(--a) + var(--d) * 0.78),
      rgba(0, 0, 0, 0.98) calc(var(--a) + var(--d) * 0.92), #000 var(--edge-to)); }
  /* where the engine has it, a tab away is skipped whole (no style, layout or paint while it waits; its scroll and
     layout kept): flipping `visibility` restyled every node of the tab on each switch (5k on a full Afisha: 65 ms) */
  @supports (content-visibility: hidden) { .tab { visibility: visible; content-visibility: hidden; } .tab.drawing { content-visibility: visible; opacity: 0; } }
  /* opacity only, backwards fill: a lingering transform fill would pin the pages (prototype bug) */
  .tab.on { visibility: visible; content-visibility: visible; z-index: auto; animation: tabIn 200ms var(--ease) backwards; }
  .view.off { display: none; }
  @keyframes tabIn { from { opacity: 0; } }
</style>
