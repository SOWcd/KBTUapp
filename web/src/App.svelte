<script lang="ts">
  // App shell: three tabs (each a pager of up to three pages), the capsule on top, the nav at the
  // bottom, one overlay stack for sheets. Telegram's Back button closes the top overlay.
  import { onMount, untrack, type Component } from 'svelte';
  import { setLucideProps } from '@lucide/svelte/context';
  import { ui, TABS, overlays, open, close, persistNav, say, type Tab } from './lib/state/ui.svelte';
  import { session, loadMe, setLoginHook, asStudent, takeAgain } from './lib/state/session.svelte';
  import { achItem } from './lib/awards';
  import { readCache, writeCache } from './lib/state/cache';
  import { data, loadAfisha, loadFriends, loadMyCard, loadNews, loadRegistry, loadStudio, loadTeam, phrase, studioChanged, friendsChanged, skipped, classKey } from './lib/state/data.svelte';
  import { burst } from './ui/burst';
  import { sheets } from './lib/state/sheets';
  import { i18n, t, subjectOf } from './lib/i18n/index.svelte';
  import { classEmoji } from './lib/i18n/subjects';
  import { classesLeft } from './lib/classes';
  import { backButton, haptic, onComputer, openLink, requestWriteAccess, tg } from './lib/tg';
  import { api, ApiErr, localize } from './lib/api';
  import { dayNo, nowTs, parts, time, at } from './lib/time';
  import Pager from './ui/Pager.svelte';
  import { CONSENT_VERSION } from './lib/legal';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Ban from '@lucide/svelte/icons/ban';
  import Nav from './ui/Nav.svelte';
  import Capsule, { type Live, type CapPage } from './ui/Capsule.svelte';
  import IconFeed from './ui/IconFeed.svelte';
  // top and bottom bars never repeat an icon (owner, Oct 21): the bottom is ticket / landmark / circle-user-round
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import Shapes from '@lucide/svelte/icons/shapes';
  import Newspaper from '@lucide/svelte/icons/newspaper';
  import LayoutDashboard from '@lucide/svelte/icons/layout-dashboard';
  import BookUser from '@lucide/svelte/icons/book-user';
  import Flag from '@lucide/svelte/icons/flag';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import Users from '@lucide/svelte/icons/users';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import IdCardLanyard from '@lucide/svelte/icons/id-card-lanyard';
  import Settings2 from '@lucide/svelte/icons/settings';
  import Toast from './ui/Toast.svelte';
  import { feedChrome, unfeed } from './ui/chrome';
  import ListPage from './screens/afisha/List.svelte';
  import Feed from './screens/afisha/Feed.svelte';
  import Clubs from './screens/afisha/Clubs.svelte';
  import Join from './screens/club/Join.svelte';
  import Me from './screens/profile/Me.svelte';
  import Friends from './screens/profile/Friends.svelte';
  import Settings from './screens/profile/Settings.svelte';
  import EventSheet from './screens/sheets/EventSheet.svelte';
  import ClubSheet from './screens/sheets/ClubSheet.svelte';
  import PersonSheet from './screens/sheets/PersonSheet.svelte';
  import LoginSheet from './screens/sheets/LoginSheet.svelte';
  import Ask from './ui/Ask.svelte';
  import { warmMap } from './lib/map';

  setLucideProps({ size: 22, strokeWidth: 1.9 });

  // sheets reachable from anywhere
  // A sheet in its own chunk needs the network the first time: offline, taps used to queue and all open on top of each
  // other once it was back (owner's list). Now only the latest tap opens, and after 2 s the app says there's no network.
  let want = 0;
  function lazy<P extends Record<string, unknown>>(load: () => Promise<{ default: Component<P> }>, props: Omit<P, 'overlay'>): void {
    const mine = ++want;
    const slow = setTimeout(() => { if (mine === want) say(t('common.offline'), 'pleading_face_3d'); }, 2000);
    load().then((m) => { clearTimeout(slow); if (mine === want) open(m.default, props); }).catch(() => { clearTimeout(slow); if (mine === want) say(t('common.offline'), 'pleading_face_3d'); });
  }
  sheets.event = (id, from) => open(EventSheet, { id, from });
  sheets.preview = (e) => open(EventSheet, { id: e.id, preview: e });
  sheets.myQr = (link, p) => lazy(() => import('./screens/profile/MyQr.svelte'), { link, p });
  sheets.person = (id) => open(PersonSheet, { id });
  sheets.club = (id) => open(ClubSheet, { id });
  // the ticket brings the QR encoder: its own chunk, fetched once the app is idle
  const ticketView = () => import('./screens/sheets/TicketView.svelte');
  sheets.ticket = (id) => lazy(ticketView, { id });
  sheets.photos = (photos, start, onremove, ongone) => lazy(() => import('./screens/sheets/PhotoViewer.svelte'), { photos, start, onremove, ongone });
  sheets.login = (after) => open(LoginSheet, { after, why: after ? 'go' : 'other' });
  sheets.pc = (ok) => lazy(() => import('./screens/sheets/PcSheet.svelte'), { ok });
  sheets.ask = (q) => new Promise((done) => { open(Ask, { ...q, done }); });
  sheets.askText = ({ placeholder, max, ...q }) => new Promise((done) => { open(Ask, { ...q, input: { placeholder, max }, done: (yes: boolean, text: string) => done(yes ? text : null) }); });
  // Studio is for club teams only: its page and views are their own chunks
  const studioPage = () => import('./screens/club/Studio.svelte');
  const teamPage = () => import('./screens/club/Team.svelte');
  const newsPage = () => import('./screens/club/News.svelte');
  const registryPage = () => import('./screens/dmp/Registry.svelte');
  // the policy changed since this student agreed: once more (staff and students added by hand have no consent of theirs)
  const askConsent = () => {
    const s = session.me?.student;
    if (s && !session.me?.deleteAt && !['staff', 'admin', CONSENT_VERSION].includes(s.consent) && !overlays.length) sheets.consent();
  };
  // the club tab's pages are chunks and that tab builds on its first tap: fetch them ahead, so it doesn't open blank
  const warmClub = () => { if (!session.me) return; void newsPage(); void studioPage(); void teamPage(); if (session.me.oversee) void registryPage(); };
  sheets.editor = (org, id) => lazy(() => import('./screens/club/EventEditor.svelte'), { org, id });
  sheets.scanner = (id, names) => lazy(() => import('./screens/club/Scanner.svelte'), { id, names });
  sheets.attendees = (id) => lazy(() => import('./screens/club/Attendees.svelte'), { id });
  sheets.manage = (id) => lazy(() => import('./screens/club/EventManage.svelte'), { id });
  sheets.memo = (org) => lazy(() => import('./screens/club/MemoSheet.svelte'), { org });
  sheets.volunteers = (id, need) => lazy(() => import('./screens/club/VolunteersSheet.svelte'), { id, need });
  sheets.memoItem = (org, kind, from, oninsert) => lazy(() => import('./screens/club/MemoItemSheet.svelte'), { org, kind, from, oninsert });
  // actions, not views: a guest is asked to sign in first, then lands in the sheet (owner, Oct 23: B1, a guest filled
  // in a whole application before the server said no)
  sheets.roundApply = (org, source) => asStudent(() => lazy(() => import('./screens/sheets/RoundApply.svelte'), { org, source }), `rc_${org}`);
  sheets.roundSetup = (org, round, onsaved) => lazy(() => import('./screens/club/RoundSetup.svelte'), { org, round, onsaved });
  sheets.roundBoard = (org) => lazy(() => import('./screens/club/RoundBoard.svelte'), { org });
  sheets.receipt = (receipt, name, ondone) => lazy(() => import('./screens/club/ReceiptSheet.svelte'), { receipt, name, ondone });
  sheets.pay = (id) => lazy(() => import('./screens/sheets/PaySheet.svelte'), { id });
  sheets.teamSetup = (org, onchange) => lazy(() => import('./screens/club/TeamSetupSheet.svelte'), { org, onchange });
  sheets.removeMember = (org, user, name, request, ondone) => lazy(() => import('./screens/club/RemoveSheet.svelte'), { org, user, name, request, ondone });
  sheets.joinInbox = (org) => lazy(() => import('./screens/club/JoinInbox.svelte'), { org });
  sheets.admin = () => lazy(() => import('./screens/admin/AdminSheet.svelte'), {});
  sheets.map = (place, exit) => lazy(() => import('./screens/map/CampusMap.svelte'), { place, exit });
  sheets.deleteAccount = (lost) => lazy(() => import('./screens/profile/DeleteSheet.svelte'), { lost });
  sheets.consent = () => lazy(() => import('./screens/sheets/ConsentSheet.svelte'), {});
  sheets.award = (it, mine) => lazy(() => import('./screens/sheets/AwardSheet.svelte'), { it, mine });
  sheets.clubEdit = (org) => lazy(() => import('./screens/club/ClubEditSheet.svelte'), { id: org });
  sheets.composer = (org, post) => lazy(() => import('./screens/club/PostComposer.svelte'), { org, post });
  sheets.createClub = () => lazy(() => import('./screens/sheets/CreateClubSheet.svelte'), {});
  sheets.academic = () => lazy(() => import('./screens/sheets/AcademicSheet.svelte'), {});
  sheets.awards = () => lazy(() => import('./screens/profile/AwardsSheet.svelte'), {});
  sheets.give = () => lazy(() => import('./screens/admin/GiveSheet.svelte'), {});
  sheets.adminClubs = () => lazy(() => import('./screens/admin/AdminClubs.svelte'), {});
  sheets.adminChats = () => lazy(() => import('./screens/admin/AdminChats.svelte'), {});
  sheets.chats = (chats) => lazy(() => import('./screens/sheets/ChatsSheet.svelte'), { chats });
  sheets.adminAi = () => lazy(() => import('./screens/admin/AdminAi.svelte'), {});
  sheets.adminTeam = () => lazy(() => import('./screens/admin/AdminTeam.svelte'), {});
  sheets.adminAudit = () => lazy(() => import('./screens/admin/AdminAudit.svelte'), {});
  sheets.suggestChat = () => lazy(() => import('./screens/sheets/SuggestChat.svelte'), {});
  sheets.roster = (org, onofficial) => lazy(() => import('./screens/dmp/Roster.svelte'), { org, onofficial });
  sheets.registry = () => lazy(() => import('./screens/dmp/RegistrySheet.svelte'), {});
  sheets.comments = (kind, id, title, onchange) => lazy(() => import('./screens/sheets/CommentsSheet.svelte'), { kind, id, title, onchange });
  sheets.inviteTo = (id, name) => asStudent(() => lazy(() => import('./screens/sheets/InviteToSheet.svelte'), { id, name }));
  sheets.report = (target, id, about, onsent) => asStudent(() => lazy(() => import('./screens/sheets/ReportSheet.svelte'), { target, id, about, onsent }));
  sheets.invite = (id, title) => lazy(() => import('./screens/sheets/InviteSheet.svelte'), { id, title });
  sheets.addFriend = (mode) => lazy(() => import('./screens/profile/AddFriend.svelte'), { share: mode === 'share' });
  sheets.look = () => lazy(() => import('./screens/profile/LookSheet.svelte'), {});
  sheets.settings = (kind) => lazy(() => import('./screens/profile/SettingsSheet.svelte'), { kind });
  setLoginHook((after) => sheets.login(after));

  // ---- tab 2 depends on who you are ----
  const member = $derived((session.me?.memberships.length ?? 0) > 0);
  const staff = $derived(!!session.me?.memberships.some((m) => m.role !== 'member'));
  // a student in no club who follows some: News, then Join (owner, Oct 13: followers had no way to the posts)
  const follower = $derived(!member && !!session.me?.student && data.orgs.some((o) => o.subscribed));
  const tab2Label = $derived(session.me?.oversee ? t('tab.dmp') : member ? (staff ? t('tab.studio') : t('tab.club')) : t('tab.join'));

  const PAGES = $derived<Record<Tab, CapPage[]>>({
    afisha: [{ label: t('page.feed'), icon: IconFeed }, { label: t('page.list'), icon: CalendarDays }, { label: t('page.clubs'), icon: Shapes }],
    club: member && session.me?.oversee  // DMP staff: the clubs registry takes the Team page's place (§4.13)
      ? [{ label: t('page.news'), icon: Newspaper }, { label: t('page.registry'), icon: BookUser }, { label: t('tab.studio'), icon: LayoutDashboard }]
      : member
      ? [{ label: t('page.news'), icon: Newspaper }, staff ? { label: t('tab.studio'), icon: LayoutDashboard } : { label: t('tab.club'), icon: Flag }, { label: t('page.team'), icon: Users }]
      : follower
      ? [{ label: t('page.news'), icon: Newspaper }, { label: t('tab.join'), icon: DoorOpen }]
      : [{ label: t('tab.join'), icon: DoorOpen }],
    profile: [{ label: t('page.friends'), icon: UsersRound, dot: (session.me?.counters.friendRequests ?? 0) > 0 }, { label: t('page.me'), icon: IdCardLanyard }, { label: t('me.settings'), icon: Settings2 }],
  });
  // a non-member's tab 2 has one page (two for a follower: News, Join): clamp where it's used, so the saved page (Studio by default) comes
  // back by itself after sign-in
  const pageIdx = (tab: Tab) => Math.min(ui.page[tab], PAGES[tab].length - 1);
  $effect(() => { void ui.tab; void ui.page.afisha; void ui.page.club; void ui.page.profile; persistNav(); });
  // the capsule says what the top overlay is (SPEC §8.2); a closing one lets go at once, so it morphs back with the exit.
  // It takes that overlay's own theme too (the map's switch), so it never sits light on a dark map.
  const capOf = $derived([...overlays].reverse().find((o) => !o.closing && o.title));
  const capTitle = $derived(ui.busy || capOf?.title || null);
  // every state has an icon (owner, Oct 21): a spinner while a tap's work runs, a sparkle if a view forgot its own
  const capIcon = $derived(ui.busy ? LoaderCircle : capOf ? (capOf.icon ?? Sparkles) : null);
  // over the Feed the nav and capsule turn into tinted dark glass (chrome.ts): at once on a tab switch,
  // and in step with the finger while the Events pager moves
  $effect(() => { feedChrome(ui.tab === 'afisha' && ui.page.afisha === 0 ? 1 : 0, 'opacity 220ms ease'); });

  // ---- live capsule: an event today you're going to, or a class within the next hour ----
  let clock = $state(nowTs());
  const live = $derived.by<Live | null>(() => {
    const now = clock;
    const today = dayNo(now);
    const ev = data.events.find((e) => e.my?.status === 'going' && e.status !== 'cancelled' && dayNo(e.startsAt) === today && (e.endsAt ?? e.startsAt + 3 * 3600) > now);
    const cls = classesLeft(data.schedule, now).find((x) => x.b - now <= 3600 && !skipped.has(classKey(today, x.c)));
    if (cls) {
      const mins = Math.ceil((cls.b - now) / 60);
      return { kind: 'class', title: subjectOf(cls.c) + (cls.c.room ? ' · ' + cls.c.room : ''), at: cls.b, emoji: classEmoji(cls.c), tint: '#2FBF71',
        label: mins > 0 ? t('cap.inMin', { n: mins }) : t('cap.until', { time: cls.c.ends }), onopen: () => { ui.tab = 'afisha'; ui.page.afisha = 1; } };
    }
    if (ev) return { kind: 'event', title: ev.title, at: ev.startsAt, emoji: ev.emoji ?? ev.org.emoji, tint: ev.tint, label: time(ev.startsAt), onopen: () => sheets.ticket(ev.id) };
    return null;
  });

  // ---- Back button: closes the top overlay ----
  $effect(() => { if (overlays.some((o) => !o.closing)) backButton.show(); else backButton.hide(); });

  // ---- greeting ----
  function greet() {
    const h = parts(nowTs()).h;
    const first = session.me?.student?.firstName;
    const name = first ? ', ' + first : '';
    const key = h < 5 ? 'say.hi.night' : h < 12 ? 'say.hi.morning' : h < 18 ? 'say.hi.day' : 'say.hi.evening';
    say(phrase(key, { name }), h < 5 ? 'crescent_moon_3d' : h < 12 ? 'sparkles_3d' : h < 18 ? 'waving_hand_3d_default' : 'partying_face_3d');
  }

  // ---- deep links: ev_<id> (event), tk_<id> (my ticket), cl_<id> (club), jr_<id> (a club's applications),
  // u_<id>_<code> (a profile: the QR on someone's badge; the code is for the door scanner), fr_<token> (a friend's
  // one-time link, §4.7), friends (the Friends page: the bot's request message) ----
  function deepLink(p = tg.startParam) {
    const j = p.match(/^join_(\d+)_([0-9a-f]{24})$/); // a club's invite link (§4.5)
    if (j) { joinByLink(Number(j[1]), j[2]); return; }
    const pr = p.match(/^pres_(\d+)_([0-9a-f]{24})$/); // a new club's one-time President link (the admin's, §2)
    if (pr) { presidentByLink(Number(pr[1]), pr[2]); return; }
    const gl = p.match(/^gl_([0-9a-f]{24})$/); // the creator's one-time award link
    if (gl) {
      ui.tab = 'profile';
      asStudent(async () => {
        try { await api.useGrantLink(gl[1]); await loadMe(); void loadMyCard(); haptic.ok(); } // loadMe brings the unlock moment
        catch { haptic.error(); say(t('give.linkDead'), 'pleading_face_3d'); }
      });
      return;
    }
    const fr = p.match(/^fr_([0-9a-f]{24})$/);
    if (fr) { friendByLink(fr[1]); return; }
    if (p === 'exit') { sheets.map(undefined, true); return; } // the owner's "help me get out" link (PLAN item 21)
    if (p === 'friends') { ui.tab = 'profile'; ui.page.profile = 0; return; }
    if (p === 'me') { ui.tab = 'profile'; ui.page.profile = 1; return; }   // the bot: "keep my account"
    if (p === 'capps') { sheets.admin(); return; }                              // the bot: a club to check
    if (p === 'achats') { sheets.adminChats(); return; }                        // the bot: suggested chats to check
    if (p === 'newclub') { asStudent(() => sheets.createClub()); return; }      // the bot: my application's answer
    const ph = p.match(/^ph_(\d+)$/); // the bot's "photos are in the album": the event, the album open over it
    if (ph) { const id = Number(ph[1]); sheets.event(id); api.event(id).then((e) => { if (e.photos.length) sheets.photos(e.photos, 0); }).catch(() => {}); return; }
    const cp = p.match(/^cp_(\d+)$/); // the bot's "someone replied" under a post: its thread
    if (cp) { asStudent(() => sheets.comments('post', Number(cp[1]), t('cm.title'))); return; }
    const cm = p.match(/^cm_(\d+)$/); // the bot's question / answer card: the event and its thread
    if (cm) { const id = Number(cm[1]); sheets.event(id); asStudent(() => { api.event(id).then((e) => sheets.comments('event', id, e.title)).catch(() => {}); }); return; }
    const aw = p.match(/^aw_([a-z0-9_]{1,40})$/); // someone's award card: my own way to the same one
    if (aw) {
      ui.tab = 'profile'; ui.page.profile = 1;
      asStudent(async () => {
        sheets.awards();
        const a = (await api.person(session.me!.id)).awards.achievements.find((x) => x.code === aw[1]);
        if (a) sheets.award(achItem(a), a.level > 0);
      });
      return;
    }
    if (p === 'news') { ui.tab = 'club'; ui.page.club = 0; return; }
    const rc = p.match(/^rc_(\d+)$/); // a club's recruitment round: a shared card, the bot's "X is recruiting"
    if (rc) { asStudent(() => sheets.roundApply(Number(rc[1]), 'link')); return; }
    const iv = p.match(/^iv_(\d+)$/); // the bot's "pick an interview time" and its reminders
    if (iv) { asStudent(() => sheets.roundApply(Number(iv[1]), 'bot')); return; }
    if (p === 'clubs') { ui.tab = 'afisha'; ui.page.afisha = 2; return; } // the bot's "other clubs recruit now"
    const mo = p.match(/^memo_(\d+)$/); // the bot's Wednesday "next week's memo is ready"
    if (mo) { asStudent(() => sheets.memo(Number(mo[1]))); return; }
    const m = p.match(/^(ev|tk|cl|jr|u|tm)_(\d+)(?:_[A-Z2-7]{10})?$/);
    // tm_<club>: the bot's removal messages open that club's Team (§2b)
    const team = (org: number) => { ui.club = org; ui.tab = 'club'; ui.page.club = 2; };
    if (m) ({ ev: sheets.event, tk: sheets.ticket, cl: sheets.club, jr: sheets.joinInbox, u: sheets.person, tm: team })[m[1] as 'ev'](Number(m[2]));
  }

  // the app was closed while away at Microsoft (the page returns to plain Telegram): someone new types the student ID
  // now, then what the guest wanted before signing in runs (owner, Oct 24)
  function msBack() {
    const again = () => { const p = takeAgain(); if (p) deepLink(p); };
    if (session.me?.msPending) sheets.login(again);
    else if (session.me?.student && !tg.startParam) again();
  }

  // the copy for the next launch follows what the screens show, a second after it settles (only once the server answered)
  let keepTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const snap = { me: session.me, events: data.events, orgs: data.orgs, schedule: data.schedule, posts: data.posts, friends: data.friends, myCard: data.myCard, news: data.news, studio: data.studio, team: data.team };
    JSON.stringify(snap); // read deeply, so any change schedules a save
    if (!booted || data.error || session.failed || session.banned) return;
    clearTimeout(keepTimer);
    keepTimer = setTimeout(() => writeCache($state.snapshot(snap)), 1000);
  });

  // another language: what is already loaded (and the cached copy) shows its translations too (PLAN 9, api/client.ts)
  $effect(() => { void i18n.lang; untrack(() => { localize(data); localize(session.me); }); });

  // ---- a new achievement level the app hasn't celebrated yet (§4.11): one moment at a time, once the app has settled ----
  // (and after signing in later: a returning student may bring one)
  let booted = $state(false), wasStudent = false;
  $effect(() => {
    const st = !!session.me?.student;
    if (st !== wasStudent) untrack(() => {
      // known to be a student (the stored copy, the server, a sign-in): Profile's and the club tab's pages fill at once
      void loadFriends(); void loadMyCard(); void loadNews();
      const club = session.me?.memberships.find((m) => m.org.id === ui.club) ?? session.me?.memberships[0];
      if (club) { void loadStudio(club.org.id); void loadTeam(club.org.id); }
      if (session.me?.oversee) void loadRegistry();
    });
    if (st && !wasStudent && booted) setTimeout(celebrate, 1600);
    wasStudent = st;
  });
  async function celebrate() {
    const me = session.me, next = me?.unlocked?.[0];
    if (!me || !next) return;
    const done = () => api.markUnlocked(next.code, next.level).then((r) => { if (session.me) session.me = { ...session.me, unlocked: r.unlocked }; setTimeout(celebrate, 700); }).catch(() => {});
    const a = (await api.person(me.id).catch(() => null))?.awards.achievements.find((x) => x.code === next.code && x.level > 0);
    if (!a) { void done(); return; }
    const m = await import('./screens/sheets/Unlock.svelte');
    open(m.default, { a, ondone: done });
  }

  function joinByLink(org: number, token: string) {
    const club = data.orgs.find((x) => x.id === org)?.name ?? '';
    asStudent(async () => {
      // already in it (my own club's link, shared or opened again): nothing to join (owner, Oct 11)
      const mine = session.me?.memberships.find((m) => m.org.id === org);
      if (mine) { say(t('join.already', { club: mine.org.name }), 'raising_hands_3d_default'); sheets.club(org); return; }
      if (!(await sheets.ask({ title: t('join.linkAsk', { club }), text: t('join.linkText'), ok: t('join.linkOk'), cancel: t('common.cancel') }))) return;
      try {
        const o = await api.acceptInvite(token);
        await loadMe(); studioChanged();
        haptic.ok(); say(t('join.linkDone', { club: o.name }), 'party_popper_3d');
        sheets.club(o.id);
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
        haptic.ok(); burst(); say(t('pres.done', { club: o.name }), 'party_popper_3d');
        ui.club = o.id; ui.tab = 'club'; ui.page.club = 1;
      } catch { haptic.error(); say(t('join.linkDead'), 'pleading_face_3d'); }
    });
  }

  /** A friend's one-time link: friends at once (the first one to open it), else why not and what to do instead. */
  function friendByLink(token: string) {
    asStudent(async () => {
      try {
        const r = await api.useFriendLink(token);
        if (r.result === 'friends') { haptic.ok(); burst(); say(t('fr.accepted', { name: r.person.name }), 'partying_face_3d'); friendsChanged(); sheets.person(r.person.id); }
        else if (r.result === 'already') { say(t('fr.already'), 'raising_hands_3d_default'); sheets.person(r.person.id); }
        else if (r.result === 'self') say(t('fr.linkSelf'), 'waving_hand_3d_default');
        else if (await sheets.ask({ title: t('fr.linkUsed'), text: t('fr.linkUsedText', { name: r.person.name }), ok: t('fr.sendRequest'), cancel: t('common.cancel') })) {
          const a = await api.askFriend(r.person.id);
          haptic.ok(); say(a.friendship === 'friends' ? t('fr.accepted', { name: r.person.name }) : t('person.requestSent'), 'raising_hands_3d_default');
          friendsChanged();
        }
      } catch { haptic.error(); say(t('fr.linkDead'), 'pleading_face_3d'); }
    });
  }

  // a computer: a sheet that the app is made for phones, with a code for the phone, until "continue on the computer"
  // (owner, Oct 11: never forbid; Oct 13: warn properly, not a toast)
  function computerHint() {
    try { if (!onComputer || localStorage.getItem('kb-pc2')) return; } catch { return; }
    sheets.pc(() => { try { localStorage.setItem('kb-pc2', '1'); } catch { /* blocked: it asks again next time */ } });
  }

  onMount(() => {
    backButton.onClick(() => close());
    // a keyboard's Esc does what Telegram's Back does (Telegram Desktop, a plain browser)
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && overlays.some((o) => !o.closing)) close(); };
    addEventListener('keydown', esc);
    // the last copy first (the instant re-open), the server's answer replaces it
    const snap = readCache();
    if (snap) {
      session.me = snap.me; session.ready = true;
      data.events = snap.events; data.orgs = snap.orgs; data.schedule = snap.schedule; data.posts = snap.posts; data.friends = snap.friends ?? null; data.myCard = snap.myCard ?? null; data.news = snap.news ?? null; data.studio = snap.studio ?? {}; data.team = snap.team ?? {}; data.eventsReady = true;
      localize(data); localize(session.me); // cached in another language, maybe
    }
    Promise.all([loadMe(), loadAfisha()]).then(() => { if (session.banned) return; if (tg.startParam !== 'exit') greet(); deepLink(); msBack(); setTimeout(ticketView, 1500); setTimeout(warmMap, 6000); setTimeout(warmClub, 3000); setTimeout(askConsent, 2200); booted = true; if (!tg.startParam) setTimeout(celebrate, 1400); setTimeout(computerHint, 1200); });
    const tick = setInterval(() => (clock = nowTs()), 30000);

    // nav shrinks to icons while scrolling down a page, comes back on the way up
    const last = new WeakMap<EventTarget, number>();
    const onScroll = (e: Event) => {
      const el = e.target as HTMLElement;
      if (!el || typeof el.scrollTop !== 'number') return;
      const y = el.scrollTop, prev = last.get(el);
      last.set(el, y);
      if (prev == null || Math.abs(y - prev) < 6) return;
      const mini = y > prev && y > 60;
      if (mini !== ui.navMini) ui.navMini = mini;
    };
    document.addEventListener('scroll', onScroll, true);

    const onPager = (e: Event) => {
      if (ui.tab !== 'afisha') return;
      const d = (e as CustomEvent).detail as { x: number; ease: string };
      feedChrome(1 - d.x, d.ease);
    };
    window.addEventListener('kb:pager', onPager);
    return () => { clearInterval(tick); document.removeEventListener('scroll', onScroll, true); window.removeEventListener('kb:pager', onPager); removeEventListener('keydown', esc); };
  });
</script>

<main class="app">
  {#each TABS as tab (tab)}
    <section class="tab" class:on={ui.tab === tab} aria-hidden={ui.tab !== tab} inert={!!session.banned}>
      <Pager count={PAGES[tab].length} index={pageIdx(tab)} active={ui.tab === tab} onchange={(i) => { ui.page[tab] = i; ui.awake++; }}>
        {#snippet page(i)}
          {#if tab === 'afisha'}
            {#if i === 0}<Feed />{:else if i === 1}<ListPage />{:else}<Clubs />{/if}
          {:else if tab === 'club'}
            {#if !member}{#if follower && i === 0}{#await newsPage() then m}<m.default />{/await}{:else}<Join />{/if}{:else if i === 0}{#await newsPage() then m}<m.default />{/await}
            {:else if session.me?.oversee}{#if i === 1}{#await registryPage() then m}<m.default />{/await}{:else}{#await studioPage() then m}<m.default />{/await}{/if}
            {:else if i === 1}{#await studioPage() then m}<m.default />{/await}{:else}{#await teamPage() then m}<m.default />{/await}{/if}
          {:else}
            {#if i === 0}<Friends />{:else if i === 1}<Me />{:else}<Settings />{/if}
          {/if}
        {/snippet}
      </Pager>
    </section>
  {/each}

  <!-- scrolled content fades under the clock and Telegram's buttons instead of running into them (owner, Oct 14);
       the same glow and background as the pages, so at rest it can't be seen; the feed's posters go full height -->
  <div class="topfade" aria-hidden="true" use:unfeed></div><div class="botfade" aria-hidden="true" use:unfeed></div>
  <div class="cap-theme {capOf?.theme ? `theme-${capOf.theme}` : ''}"><Capsule pages={PAGES[ui.tab]} index={pageIdx(ui.tab)} onpick={(i) => (ui.page[ui.tab] = i)} {live} title={capTitle} icon={capIcon} spin={!!ui.busy} /></div>
  <Nav labels={[t('tab.afisha'), tab2Label, t('tab.profile')]} dot={[false, (session.me?.counters.unreadBroadcasts ?? 0) > 0, (session.me?.counters.friendRequests ?? 0) > 0 || (session.me?.counters.reports ?? 0) + (session.me?.counters.clubApps ?? 0) > 0]} />

  {#each overlays as o (o.id)}
    <o.component {...o.props} overlay={o} />
  {/each}
  <Toast />
  {#if session.banned}
    <div class="banned" role="alertdialog" aria-labelledby="ban-t">
      <span class="bico"><Ban size={34} /></span>
      <h2 id="ban-t" class="t-h2">{t('ban.title')}</h2>
      {#if session.banned.reason}<p class="t-callout">{t('ban.reason', { reason: session.banned.reason })}</p>{/if}
      {#if session.banned.contact}<button class="bapp" onclick={() => openLink('https://t.me/' + session.banned!.contact)}>{t('ban.appeal')}</button>{/if}
      <p class="t-foot">{t('ban.data')}</p>
    </div>
  {/if}
</main>

<style>
  .cap-theme { display: contents; }
  .banned { position: absolute; inset: 0; z-index: 10000; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px;
    padding: 24px; text-align: center; background: var(--glow), var(--bg); }
  .bico { width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger-text); }
  .banned p { max-width: 320px; color: var(--text-2); overflow-wrap: anywhere; }
  .bapp { margin-top: 8px; height: 44px; padding: 0 20px; border-radius: var(--r-full); background: var(--surface-2); font: 650 15px/1 var(--font-text); }
  .topfade { position: absolute; inset: 0; z-index: calc(var(--z-capsule) - 1); pointer-events: none; background: var(--glow), var(--bg);
    -webkit-mask-image: linear-gradient(#000 calc(var(--top) - 4px), transparent calc(var(--top) + 36px));
    mask-image: linear-gradient(#000 calc(var(--top) - 4px), transparent calc(var(--top) + 36px)); }
  /* and under the bottom bar, softer: the glass still has something to bend (mockup v23) */
  .botfade { position: absolute; inset: 0; z-index: calc(var(--z-nav) - 1); pointer-events: none; background: var(--bg);
    -webkit-mask-image: linear-gradient(0deg, rgba(0, 0, 0, 0.85), transparent calc(var(--bottom) + 40px));
    mask-image: linear-gradient(0deg, rgba(0, 0, 0, 0.85), transparent calc(var(--bottom) + 40px)); }
  .app { position: absolute; inset: 0; overflow: hidden; background: var(--bg); }
  .tab { position: absolute; inset: 0; visibility: hidden; pointer-events: none; }
  /* opacity only, backwards fill: a lingering transform fill would pin the pager pages (prototype bug) */
  .tab.on { visibility: visible; pointer-events: auto; animation: tabIn 200ms var(--ease) backwards; }
  @keyframes tabIn { from { opacity: 0; } }
</style>
