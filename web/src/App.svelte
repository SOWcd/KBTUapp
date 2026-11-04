<script lang="ts">
  // App shell: the tabs (one scrolling screen each; what used to be their other pages opens as a sheet), the capsule on
  // top, the nav at the bottom, one overlay stack for sheets. Telegram's Back button closes the top overlay.
  import { onMount, untrack, type Component } from 'svelte';
  import { setLucideProps } from '@lucide/svelte/context';
  import { ui, TABS, overlays, open, close, persistNav, say, moment, backTo, type Tab } from './lib/state/ui.svelte';
  import { session, loadMe, setLoginHook, asStudent, takeAgain } from './lib/state/session.svelte';
  import { achItem } from './lib/awards';
  import { readCache, writeCache } from './lib/state/cache';
  import { channel, loadChannel } from './lib/state/channel.svelte';
  import { data, loadAfisha, loadFriends, loadMyCard, loadNews, loadInbox, loadRegistry, loadStudio, loadTeam, phrase, studioChanged, eventById, toggleGoing, keepRef, friendsChanged, skipped, classKey } from './lib/state/data.svelte';
  import { burst } from './ui/burst';
  import { nameOf } from './lib/short';
  import { sheets } from './lib/state/sheets';
  import { i18n, t, subjectOf } from './lib/i18n/index.svelte';
  import { classEmoji } from './lib/i18n/subjects';
  import { classesLeft } from './lib/classes';
  import { backButton, haptic, onComputer, openLink, requestWriteAccess, tg } from './lib/tg';
  import { api, ApiErr, localize, type Id } from './lib/api';
  import { dayNo, nowTs, parts, time, at } from './lib/time';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import Ban from '@lucide/svelte/icons/ban';
  import Nav from './ui/Nav.svelte';
  import Capsule, { type Live } from './ui/Capsule.svelte';
  import { TAB_ICON } from './ui/icons';
  import KbtuMark from './ui/KbtuMark.svelte';
  import Toast from './ui/Toast.svelte';
  import { feedChrome, unfeed } from './ui/chrome';
  import ListPage from './screens/afisha/List.svelte';
  import Clubs from './screens/afisha/Clubs.svelte';
  import Me from './screens/profile/Me.svelte';
  import LoginSheet from './screens/sheets/LoginSheet.svelte';
  import Ask from './ui/Ask.svelte';
  import { warmMap } from './lib/map';

  setLucideProps({ size: 22, strokeWidth: 2 }); // stroke 2 everywhere (the design system, Oct 30; was 1.9)

  // sheets reachable from anywhere
  // A sheet in its own chunk needs the network the first time: offline, taps used to queue and all open on top of each
  // other once it was back. Now only the latest tap opens, and after 2 s the app says there's no network.
  let want = 0;
  // a chunk already loaded opens in the tap's own task: import() resolves a task later even then
  const loaded = new Map<() => Promise<unknown>, { default: Component<any> }>();
  // (the promise settles once it's open or given up: a queued moment waits for it, lib/moments.ts)
  function lazy<P extends Record<string, unknown>>(load: () => Promise<{ default: Component<P> }>, props: Omit<P, 'overlay'>): Promise<void> {
    const mine = ++want, got = loaded.get(load);
    if (got) { open(got.default, props); return Promise.resolve(); }
    const slow = setTimeout(() => { if (mine === want) say(t('common.offline'), 'pleading_face_3d'); }, 2000);
    return load().then((m) => { clearTimeout(slow); loaded.set(load, m); if (mine === want) open(m.default, props); }).catch(() => { clearTimeout(slow); if (mine === want) say(t('common.offline'), 'pleading_face_3d'); });
  }
  // the event, person and club sheets are chunks too (out of the start's bundle), fetched with the first API calls (onMount),
  // so by any tap, or a deep link (it waits for those calls), they open in the same frame as before
  const eventSheet = () => import('./screens/sheets/EventSheet.svelte');
  const personSheet = () => import('./screens/sheets/PersonSheet.svelte');
  const clubSheet = () => import('./screens/sheets/ClubSheet.svelte');
  sheets.event = (id, from) => lazy(eventSheet, { id, from });
  sheets.preview = (e) => lazy(eventSheet, { id: e.id, preview: e });
  sheets.myQr = (link, p) => lazy(() => import('./screens/profile/MyQr.svelte'), { link, p });
  sheets.cropPhoto = (file) => new Promise((done) => lazy(() => import('./screens/profile/PhotoCrop.svelte'), { file, done }));
  sheets.person = (id, invite) => lazy(personSheet, { id, invite });
  sheets.club = (id) => lazy(clubSheet, { id });
  // the ticket brings the QR encoder: its own chunk, fetched once the app is idle
  const ticketView = () => import('./screens/sheets/TicketView.svelte');
  sheets.ticket = (id) => lazy(ticketView, { id });
  sheets.stories = (groups, start, at) => lazy(() => import('./screens/sheets/Stories.svelte'), { groups, start, at });
  sheets.photos = (photos, start, onremove, ongone) => lazy(() => import('./screens/sheets/PhotoViewer.svelte'), { photos, start, onremove, ongone });
  sheets.login = (after, lock) => open(LoginSheet, { after, why: after ? 'go' : 'other', lock });
  const pcSheet = () => import('./screens/sheets/PcSheet.svelte');
  sheets.ask = (q) => new Promise((done) => { open(Ask, { ...q, done }); });
  sheets.answers = (title, questions) => new Promise((done) => lazy(() => import('./screens/sheets/AnswersSheet.svelte'), { title, questions, done }));
  sheets.askText = ({ placeholder, max, tel, value, line, ...q }) => new Promise((done) => { open(Ask, { ...q, input: { placeholder, max, tel, value, line }, done: (yes: boolean, text: string) => done(yes ? text : null) }); });
  // a club's Studio is for its members only: its page and views are their own chunks
  const studioPage = () => import('./screens/club/StudioPane.svelte');
  sheets.studio = (org) => lazy(studioPage, { org });
  const teamPage = () => import('./screens/club/Team.svelte');
  const feedPage = () => import('./screens/afisha/Feed.svelte');
  // what used to be pages beside a tab's screen: named loaders, warmed ahead, so their sheets open in the tap's frame
  const newsPage = () => import('./screens/afisha/News.svelte');
  const friendsPage = () => import('./screens/profile/Friends.svelte');
  const settingsList = () => import('./screens/profile/SettingsList.svelte'); // the settings under my lanyard (Me)
  const channelPage = () => import('./screens/forum/Channel.svelte'); // the forum: posts to the public channel, its own tab (Nov 1)
  // the policy changed since this student agreed: the whole app waits behind the gate until they accept (owner, Nov 1:
  // the sheet got swiped away unread). Staff and students added by hand have no consent of theirs; a deletion pending is
  // exempt. Only on the server's word (boardKnown): the launch copy's policy is the default, not the one in force.
  const consentGate = () => import('./screens/ConsentGate.svelte');
  const gated = $derived.by(() => {
    const s = session.me?.student;
    return !!s && session.boardKnown && !session.me?.deleteAt && !['staff', 'admin', session.policy].includes(s.consent);
  });
  $effect(() => { ui.gate = gated; });
  // while gated no overlay shows: they wait in the stack and show after "Accept" (a deep link isn't lost)
  const shown = (_o: unknown) => !gated;
  // a club's Studio pane and its Team are chunks: fetch them ahead, so they open in the tap's frame;
  // the Feed, News, Friends and the settings list too (pages once, sheets now), so they open in the tap's frame
  const warm = (load: () => Promise<{ default: Component<any> }>) => void load().then((m) => loaded.set(load, m)).catch(() => {});
  const warmPages = () => { [feedPage, newsPage, friendsPage, settingsList].forEach(warm); if (!session.me?.memberships.length) return; warm(studioPage); warm(teamPage); };
  // the forum's chunk and its feed with the app, so the tab opens full (the speed rule)
  const warmChannel = () => { if (!session.channel) return; void channelPage(); void loadChannel(); };
  sheets.editor = (org, id) => lazy(() => import('./screens/club/EventEditor.svelte'), { org, id });
  sheets.scanner = (id, names) => lazy(() => import('./screens/club/Scanner.svelte'), { id, names });
  sheets.scannerOnly = (id) => lazy(() => import('./screens/club/Scanner.svelte'), { id, only: true });
  sheets.crew = (id, onchange) => lazy(() => import('./screens/club/CrewSheet.svelte'), { id, onchange });
  sheets.mapFlaws = () => lazy(() => import('./screens/admin/MapFlaws.svelte'), {});
  sheets.assistant = (ctx) => asStudent(() => lazy(() => import('./screens/assistant/Assistant.svelte'), { ctx }));
  sheets.attendees = (id) => lazy(() => import('./screens/club/Attendees.svelte'), { id });
  sheets.screens = (code, event) => lazy(() => import('./screens/club/ScreenSheet.svelte'), { code, event });
  sheets.manage = (id) => lazy(() => import('./screens/club/EventManage.svelte'), { id });
  sheets.memo = (org) => lazy(() => import('./screens/club/MemoSheet.svelte'), { org });
  const rosterWelcome = () => import('./screens/sheets/RosterWelcome.svelte'), rosterAsk = () => import('./screens/sheets/RosterAsk.svelte');
  sheets.rosterRequests = (ondone, org) => lazy(() => import('./screens/club/RosterRequests.svelte'), { ondone, org });
  sheets.volunteers = (id, need) => lazy(() => import('./screens/club/VolunteersSheet.svelte'), { id, need });
  sheets.memoItem = (org, kind, from, oninsert) => lazy(() => import('./screens/club/MemoItemSheet.svelte'), { org, kind, from, oninsert });
  // actions, not views: a guest is asked to sign in first, then lands in the sheet (owner, Oct 23: B1, a guest filled
  // in a whole application before the server said no)
  sheets.roundApply = (org, source) => asStudent(() => void quickApply(org, source), `rc_${org}`);
  // a round with nothing to answer or pick (round.quick): one tap sends it, no confirm (owner, Nov 3); the button turns
  // "Sent" at once, the toast says what the club sees, with an Undo (it withdraws). Anything else, or a sent one, opens the sheet
  async function quickApply(org: Id, source = 'club') {
    const sheet = () => lazy(() => import('./screens/sheets/RoundApply.svelte'), { org, source });
    const o = data.orgs.find((x) => x.id === org);
    if (!o?.round?.quick || o.round.applied) return sheet();
    const round = o.round, mark = (applied: boolean) => { const x = data.orgs.find((y) => y.id === org); if (x?.round?.id === round.id) x.round = { ...x.round, applied }; };
    mark(true); haptic.ok();
    try {
      await api.applyRound(round.id, { departments: [], answers: {}, source });
      burst(); void loadAfisha();
      say(t('cast.sentShares'), 'party_popper_3d', () => {
        mark(false); haptic.soft();
        api.withdrawRound(round.id).then(() => void loadAfisha()).catch(() => { mark(true); say(t('common.error'), 'warning_3d'); });
      });
    } catch (x) {
      mark(false);
      // the round changed meanwhile (questions or departments since): its sheet
      if (x instanceof ApiErr && x.code === 'bad_input') { void loadAfisha(); return sheet(); }
      haptic.error(); say(x instanceof ApiErr && x.code === 'closed' ? t('cast.closed') : t('common.error'), 'warning_3d');
    }
  }
  sheets.roundSetup = (org, round, onsaved) => lazy(() => import('./screens/club/RoundSetup.svelte'), { org, round, onsaved });
  sheets.roundBoard = (org) => lazy(() => import('./screens/club/RoundBoard.svelte'), { org });
  sheets.receipt = (receipt, name, ondone) => lazy(() => import('./screens/club/ReceiptSheet.svelte'), { receipt, name, ondone });
  sheets.pay = (id) => lazy(() => import('./screens/sheets/PaySheet.svelte'), { id });
  sheets.teamSetup = (org, onchange) => lazy(() => import('./screens/club/TeamSetupSheet.svelte'), { org, onchange });
  sheets.removeMember = (org, user, name, request, ondone) => lazy(() => import('./screens/club/RemoveSheet.svelte'), { org, user, name, request, ondone });
  sheets.joinInbox = (org) => lazy(() => import('./screens/club/JoinInbox.svelte'), { org });
  sheets.admin = () => lazy(() => import('./screens/admin/AdminSheet.svelte'), {});
  sheets.map = (place, exit) => { warmMap(); return lazy(() => import('./screens/map/CampusMap.svelte'), { place, exit }); };
  sheets.deleteAccount = (lost) => lazy(() => import('./screens/profile/DeleteSheet.svelte'), { lost });
  sheets.consent = () => void loadMe();
  sheets.award = (it, mine) => lazy(() => import('./screens/sheets/AwardSheet.svelte'), { it, mine });
  sheets.clubEdit = (org, at) => lazy(() => import('./screens/club/ClubEditSheet.svelte'), { id: org, at });
  sheets.people = (org, title) => lazy(() => import('./screens/sheets/PeopleSheet.svelte'), { org, title });
  sheets.composer = (org, post) => lazy(() => import('./screens/club/PostComposer.svelte'), { org, post });
  sheets.createClub = () => lazy(() => import('./screens/sheets/CreateClubSheet.svelte'), {});
  sheets.academic = () => lazy(() => import('./screens/sheets/AcademicSheet.svelte'), {});
  sheets.anthem = () => lazy(() => import('./screens/sheets/AnthemSheet.svelte'), {});
  sheets.awards = () => lazy(() => import('./screens/profile/AwardsSheet.svelte'), {});
  sheets.adminAwards = sheets.give = sheets.badges = () => lazy(() => import('./screens/admin/AdminAwards.svelte'), {});
  sheets.adminClubs = (at) => lazy(() => import('./screens/admin/AdminClubs.svelte'), { at });
  sheets.adminChats = () => lazy(() => import('./screens/admin/AdminChats.svelte'), {});
  sheets.adminForum = () => lazy(() => import('./screens/admin/AdminForum.svelte'), {});
  sheets.schedHowTo = () => lazy(() => import('./screens/sheets/ScheduleHowTo.svelte'), {});
  sheets.week = () => lazy(() => import('./screens/sheets/WeekSheet.svelte'), {});
  sheets.forum = (ask) => lazy(() => import('./screens/forum/Forum.svelte'), { ask });
  sheets.forumSkills = (onsaved) => lazy(() => import('./screens/forum/SkillsSheet.svelte'), { onsaved });
  sheets.newAsk = (onmade) => lazy(() => import('./screens/forum/NewAsk.svelte'), { onmade });
  sheets.channelPost = (draft) => lazy(() => import('./screens/forum/ChannelCompose.svelte'), { draft });
  sheets.channelReply = (post) => lazy(() => import('./screens/forum/ChannelReply.svelte'), { post });
  sheets.askPeople = (ask, title) => lazy(() => import('./screens/forum/AskPeople.svelte'), { ask, title });
  sheets.chats = (chats) => lazy(() => import('./screens/sheets/ChatsSheet.svelte'), { chats });
  sheets.myClubs = (rows) => lazy(() => import('./screens/afisha/MyClubs.svelte'), { rows });
  sheets.adminAi = () => lazy(() => import('./screens/admin/AdminAi.svelte'), {});
  sheets.adminAudit = () => lazy(() => import('./screens/admin/AdminAudit.svelte'), {});
  sheets.suggestChat = () => lazy(() => import('./screens/sheets/SuggestChat.svelte'), {});
  sheets.roster = (org, onofficial) => lazy(() => import('./screens/dmp/Roster.svelte'), { org, onofficial });
  sheets.registry = () => lazy(() => import('./screens/dmp/RegistrySheet.svelte'), {});
  sheets.comments = (kind, id, title, onchange) => lazy(() => import('./screens/sheets/CommentsSheet.svelte'), { kind, id, title, onchange });
  sheets.inviteTo = (id, name) => asStudent(() => lazy(() => import('./screens/sheets/InviteToSheet.svelte'), { id, name }));
  sheets.report = (target, id, about, onsent) => asStudent(() => lazy(() => import('./screens/sheets/ReportSheet.svelte'), { target, id, about, onsent }));
  sheets.invite = (id, title) => lazy(() => import('./screens/sheets/InviteSheet.svelte'), { id, title });
  sheets.celebrate = () => void celebrate();
  sheets.referral = (code) => lazy(() => import('./screens/profile/RefSheet.svelte'), { code });
  sheets.addFriend = (mode) => lazy(() => import('./screens/profile/AddFriend.svelte'), { share: mode === 'share' });
  sheets.settings = (kind) => lazy(() => import('./screens/profile/SettingsSheet.svelte'), { kind });
  sheets.news = () => lazy(newsPage, {});
  sheets.feed = () => lazy(feedPage, {});
  sheets.friends = () => lazy(friendsPage, {});
  sheets.team = () => lazy(teamPage, {});
  setLoginHook((after, lock) => sheets.login(after, lock));

  // ---- the Clubs tab: one feed for everyone; a club of mine opens its Studio pushed over it (round 5) ----
  // the bar's tabs: the forum only where the server opened it (FORUM_CHANNEL; its policy section in force)
  const tabs = $derived(TABS.filter((k) => k !== 'forum' || session.channel));
  $effect(() => { if (session.boardKnown && !session.channel && ui.tab === 'forum') ui.tab = 'afisha'; }); // the server's word, not the launch copy's
  // a role changes a tab's content, never its name
  const TAB_LABEL: Record<Tab, () => string> = { afisha: () => t('tab.afisha'), forum: () => t('tab.forum'), club: () => t('page.clubs'), profile: () => t('tab.profile') };
  const TAB_DOT: Record<Tab, () => boolean> = {
    afisha: () => (session.me?.counters.unreadBroadcasts ?? 0) > 0, forum: () => false, club: () => false,
    profile: () => (session.me?.counters.friendRequests ?? 0) > 0 || (session.me?.counters.inbox ?? 0) > 0,
  };
  /** A club of mine: the Clubs tab with its Studio pushed over it. */
  function toClub(org: number) { ui.tab = 'club'; sheets.studio(org); }
  // a screen builds on its first showing and stays alive (scroll kept); a tab never shown builds nothing (the hidden tabs
  // were ~1400 of 1900 nodes and 40 % of the blocking time at start)
  const built = $state<Record<string, boolean>>({});
  // (the Clubs tab waits for who I am: the copy or the server, a frame; else a member's hidden catalogue built too)
  $effect(() => { if (ui.tab === 'club' && !session.ready) return; if (!built[ui.tab]) built[ui.tab] = true; });
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
    if (!k || session.banned) return;
    built[k] = true;
    idle(() => {
      if (ui.tab === k) { idle(prebuild); return; }
      drawing = k;
      requestAnimationFrame(() => setTimeout(() => { drawing = null; idle(prebuild); }));
    });
  }
  $effect(() => { void ui.tab; void ui.club; persistNav(); });
  // the capsule says what the top overlay is (SPEC §8.2); a closing one lets go at once, so it morphs back with the exit.
  // It takes that overlay's own theme too (the map's switch), so it never sits light on a dark map.
  // The top overlay that speaks decides (a Pane at rest is quiet but still the top: the capsule never names the page
  // under it); a menu or an Ask says nothing and lets the one below speak.
  const capOf = $derived([...overlays].reverse().find((o) => !o.closing && (o.title || o.quiet)));
  // over the Feed the capsule turns into tinted dark glass (chrome.ts); a titled overlay over it (the map, a sheet) takes
  // the normal chrome (owner's video, Oct 25: the map's capsule kept the Feed's tint)
  $effect(() => { feedChrome(capOf?.feed ? 1 : 0, 'opacity 220ms ease'); });

  // ---- live capsule: an event today you're going to, or a class within the next hour ----
  let clock = $state(nowTs());
  const live = $derived.by<Live | null>(() => {
    const now = clock;
    const today = dayNo(now);
    const ev = data.events.find((e) => e.my?.status === 'going' && e.status !== 'cancelled' && dayNo(e.startsAt) === today && (e.endsAt ?? e.startsAt + 3 * 3600) > now
      && (e.endsAt ?? e.startsAt) - e.startsAt < 86400); // not one of several days (a casting over a week: owner, Nov 3)
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
  const capTitle = $derived(ui.busy || (capOf ? (capOf.mark ? null : capOf.title) : live ? null : TAB_LABEL[ui.tab]()) || null);
  // a spinner while a tap's work runs; a view that forgot its own icon gets the app's mark (Sparkles is the assistant's alone)
  const capIcon = $derived(ui.busy ? LoaderCircle : capOf ? (capOf.icon ?? KbtuMark) : TAB_ICON[ui.tab]);

  // ---- Back button: closes the top overlay ----
  $effect(() => { if (overlays.some((o) => !o.closing && !o.holdBack && shown(o)) || backTo.fn) backButton.show(); else backButton.hide(); });

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
  function greet() {
    const h = parts(nowTs()).h;
    const first = session.me?.student?.firstName;
    const name = first ? ', ' + first : '';
    const key = h < 5 ? 'say.hi.night' : h < 12 ? 'say.hi.morning' : h < 18 ? 'say.hi.day' : 'say.hi.evening';
    say(phrase(key, { name }), h < 5 ? 'crescent_moon_3d' : h < 12 ? 'sparkles_3d' : h < 18 ? 'waving_hand_3d_default' : 'partying_face_3d');
  }

  // ---- deep links: ev_<id> (event), tk_<id> (my ticket), cl_<id> (club), jr_<id> (a club's applications),
  // u_<id>_<code> (a profile: the QR on someone's badge; the code is for the door scanner), fr_<token> (a friend's
  // one-time link, §4.7), friends (Profile with the Friends sheet: the bot's request message) ----
  function deepLink(p = tg.startParam) {
    const j = p.match(/^join_(\d+)_([0-9a-f]{24})$/); // a club's invite link (§4.5)
    if (j) { joinByLink(Number(j[1]), j[2]); return; }
    const pr = p.match(/^pres_(\d+)_([0-9a-f]{24})$/); // a new club's one-time President link (the admin's, §2)
    if (pr) { presidentByLink(Number(pr[1]), pr[2]); return; }
    const gl = p.match(/^gl_([0-9a-f]{24})$/); // the creator's award link (one-time, or many's: admin claim new)
    if (gl) {
      ui.tab = 'profile';
      asStudent(async () => {
        try { await api.useGrantLink(gl[1]); await loadMe(); void loadMyCard(); haptic.ok(); } // loadMe brings the unlock moment
        catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'conflict' ? t('give.already') : t('give.linkDead'), 'pleading_face_3d'); } // mine already: the link stays for whom it was meant
      }, p); // a guest's Microsoft sign-in round trip keeps the link (takeAgain)
      return;
    }
    const fr = p.match(/^fr_([0-9a-f]{24})$/);
    if (fr) { friendByLink(fr[1]); return; }
    if (p === 'exit') { sheets.map(undefined, true); return; } // the owner's "help me get out" link (PLAN item 21)
    if (p === 'friends') { ui.tab = 'profile'; sheets.friends(); return; }
    if (p === 'me') { ui.tab = 'profile'; return; }   // the bot: "keep my account"
    if (p === 'cm') return; // the bot's "register" under a deleted Telegram comment: the comment's card is a launch moment (tgComment)
    if (p === 'anthem') { sheets.anthem(); return; } // the volunteers' chat link: the anthem over the tab as it is, guests too
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
      ui.tab = 'profile';
      asStudent(async () => {
        sheets.awards();
        // an older card may name a badge's variant (aw_init26f): its badge
        const a = (await api.person(session.me!.id)).awards.achievements.find((x) => x.code === aw[1] || x.variants?.some((v) => v.code === aw[1]));
        if (a) sheets.award(achItem(a), a.level > 0);
      });
      return;
    }
    if (p === 'news') { ui.tab = 'afisha'; sheets.news(); return; } // every post: Afisha's "All" 
    if (/^ci_\d+_\d+_[0-9a-f]{16}$/.test(p)) { void checkIn(p); return; } // the big screen's QR (server checkin.py)
    const sh = p.match(/^sh_([0-9a-f]{16})$/); // /show's pairing QR: only a session's organizers bind it
    if (sh) { asStudent(() => sheets.screens(sh[1])); return; }
    const fp = p.match(/^fp(?:_(\d+))?$/); // the bot's first comment under a post: the Forum tab, that post in view (bare fp: the tab)
    if (fp) { channel.focus = fp[1] ? Number(fp[1]) : null; if (session.channel) ui.tab = 'forum'; return; }
    const fa = p.match(/^fa_(\d+)$/); // the bot's ping or "your request is hidden": the forum, that request in sight
    if (fa) { asStudent(() => sheets.forum(Number(fa[1]))); return; }
    const rf = p.match(/^r_([A-Z2-7]{10})$/); // someone's invite link (Nov 2: the one link): noted for them as a referral,
    if (rf) {                                 // and their card with "Add as a friend" (opening adds nobody); my own: nothing
      void api.refer(rf[1]).catch(() => {});
      api.linkCard(rf[1]).then((card) => { if (card.friendship !== 'self') sheets.person(card.person.id, { code: rf[1], card }); })
        .catch(() => say(t('fr.linkDead'), 'pleading_face_3d'));
      return;
    }
    if (p === 'sched') { asStudent(() => { void loadAfisha().then(() => sheets.week()); }); return; } // the bot read my week: check it
    if (p === 'rq') { asStudent(() => sheets.rosterRequests()); return; } // the bot: someone says they're in our DMP list
    const ce = p.match(/^ce_(\d+)$/); // the bot's "chat linked to your club": Studio's chats, for "show posts in the feed"
    if (ce) { asStudent(() => sheets.clubEdit(Number(ce[1]), 'chats')); return; }
    const rc = p.match(/^rc_(\d+)$/); // a club's recruitment round: a shared card, the bot's "X is recruiting"
    if (rc) { asStudent(() => sheets.roundApply(Number(rc[1]), 'link')); return; }
    const iv = p.match(/^iv_(\d+)$/); // the bot's "pick an interview time" and its reminders
    if (iv) { asStudent(() => sheets.roundApply(Number(iv[1]), 'bot')); return; }
    if (p === 'clubs') { ui.tab = 'club'; return; } // the bot's "other clubs recruit now"
    if (p === 'chats') { // the bot's "your suggested chat is in the app": the chats directory
      ui.tab = 'club';
      void api.chats().then((c) => { data.chats = c; sheets.chats(c.all); }).catch(() => {});
      return;
    }
    const mo = p.match(/^memo_(\d+)$/); // the bot's Wednesday "next week's memo is ready"
    if (mo) { asStudent(() => sheets.memo(Number(mo[1]))); return; }
    const ref = p.match(/^ev_(\d+)_([A-Z2-7]{10})$/); // a club member's "My link": the sign-up goes to them
    if (ref) keepRef(Number(ref[1]), ref[2]);
    const qr = p.match(/^u_(\d+_[A-Z2-7]{10})$/); // someone's profile QR (the invite sheet shows it too): noted for them as an invite
    if (qr) void api.refer(qr[1]).catch(() => {});
    const m = p.match(/^(ev|tk|cl|jr|u|tm|st)_(\d+)(?:_[A-Z2-7]{10})?$/);
    // tm_<club>: the bot's removal messages open that club's Team (§2b) over its Studio; no longer in it: the club's page
    // (the Team once the Studio pane is open: two chunk loads at once, lazy() opens only the later one, and Team reads
    // ui.club, which the pane sets: a cold start opened another club's Team, no Studio under it)
    const team = (org: number) => {
      if (!session.me?.memberships.some((x) => x.org.id === org)) { sheets.club(org); return; }
      ui.tab = 'club'; ui.club = org; void lazy(studioPage, { org }).then(() => sheets.team());
    };
    // st_<club>: the bot's "host an event with us": that club's Studio, whose To do answers it
    const studio = (org: number) => {
      if (!session.me?.memberships.some((x) => x.org.id === org)) { sheets.club(org); return; }
      ui.tab = 'club'; ui.club = org; void lazy(studioPage, { org });
    };
    if (m) ({ ev: sheets.event, tk: sheets.ticket, cl: sheets.club, jr: sheets.joinInbox, u: sheets.person, tm: team, st: studio })[m[1] as 'ev'](Number(m[2]));
    // a link the app doesn't know (cut, mistyped, or from something since gone): said, not silently dropped (owner, Oct 30)
    else if (p) say(t('link.unknown'), 'thinking_face_3d');
  }

  // the app was closed while away at Microsoft (the page returns to plain Telegram): someone new types the student ID
  // now, then what the guest wanted before signing in runs
  // A scan of the big screen's QR: the server keeps it at once; a guest signs in (the sheet comes back to Telegram by
  // itself) and the same scan again shows it counted (the server counted it at the sign-up already)
  async function checkIn(p: string, again = false): Promise<void> {
    try {
      const r = await api.qrCheckin(p);
      if (r.done && r.left) { haptic.ok(); say(t('ci.left', { title: r.title }), 'waving_hand_3d_default'); return; }
      if (r.done) { haptic.ok(); say(t('ci.done', { title: r.title }), 'party_popper_3d'); return; }
      if (!again) { say(t('ci.wait', { title: r.title }), 'waving_hand_3d_default'); asStudent(() => void checkIn(p, true), p, true); }
    } catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.code === 'closed' ? t('ci.closed') : e instanceof ApiErr && e.message === 'qr_old' ? t('ci.old') : e instanceof ApiErr && e.message === 'qr_not_in' ? t('ci.notIn') : t('common.error'), 'warning_3d');
    }
  }

  function msBack() {
    // go_<id>: a guest's "I'm going" from before the sign-in, kept on the phone only (never a start param: a shared link
    // must not sign anyone up)
    const again = () => {
      const p = takeAgain(), go = p?.match(/^go_(\d+)$/);
      if (!go) { if (p) deepLink(p); return; }
      const id = Number(go[1]), st = eventById(id)?.my?.status;
      sheets.event(id);
      if (st !== 'going' && st !== 'hold' && st !== 'waitlist') toggleGoing(id, () => sheets.pay(id));
    };
    if (session.me?.msPending) sheets.login(again);
    else if (session.me?.student && !tg.startParam) again();
  }

  // the copy for the next launch follows what the screens show, a second after it settles (only once the server answered).
  // The effect reads only the lists' references and data.kept (a tap's change inside a list): no deep read before the
  // paint; the JSON is made when the app is idle, and again as it goes to the background.
  // ponytail: a change deep inside a list that bumps no data.kept waits for the next reload or the background; bump it there if one matters
  const snap = () => ({ me: session.me, events: data.events, orgs: data.orgs, schedule: data.schedule, posts: data.posts, friends: data.friends, myCard: data.myCard, news: data.news, studio: data.studio, team: data.team });
  const keepable = () => booted && !data.error && !session.failed && !session.banned;
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
    return () => document.removeEventListener('visibilitychange', away);
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
      void loadInbox(true); // staff only (it checks)
    });
    if (st && !wasStudent && booted) { moment(tgComment); moment(celebrate); } // signed in just now: his comment first
    wasStudent = st;
  });
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
        toClub(o.id);
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
  // (never forbid; warn properly, not a toast)
  function computerHint() {
    try { if (!onComputer || localStorage.getItem('kb-pc2')) return; } catch { return; }
    return lazy(pcSheet, { ok: () => { try { localStorage.setItem('kb-pc2', '1'); } catch { /* blocked: it asks again next time */ } } });
  }

  onMount(() => {
    backButton.onClick(() => { if (!overlays.some((o) => !o.closing) && backTo.fn) backTo.fn(); else close(); });
    // a keyboard's Esc does what Telegram's Back does (Telegram Desktop, a plain browser)
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && overlays.some((o) => !o.closing && shown(o))) close(); };
    addEventListener('keydown', esc);
    // the last copy first (the instant re-open), the server's answer replaces it
    const snap = readCache();
    if (snap) {
      session.me = snap.me; session.ready = true; session.board = !!snap.me?.board; session.channel = !!snap.me?.forumChannel; // the last launch's word until the server's
      data.events = snap.events; data.orgs = snap.orgs; data.schedule = snap.schedule; data.posts = snap.posts; data.friends = snap.friends ?? null; data.myCard = snap.myCard ?? null; data.news = snap.news ?? null; data.studio = snap.studio ?? {}; data.team = snap.team ?? {}; data.eventsReady = true;
      localize(data); localize(session.me); // cached in another language, maybe
    }
    Promise.all([loadMe(), loadAfisha()]).then(() => {
      // the sheets a first tap opens, warmed once the first data is in: at mount their ~35 chunks shared a slow line with it
      for (const load of [eventSheet, personSheet, clubSheet]) load().then((m) => loaded.set(load, m)).catch(() => {});
      if (session.banned) return;
      // one toast at the start, and none on a launch that opens something itself (a link, the sign-up's ID form)
      if (!tg.startParam && !session.me?.msPending && !gated && !session.tgComment) greet(); // (not over the policy gate's button, nor my Telegram comment's card)
      deepLink(); msBack(); setTimeout(ticketView, 1500); setTimeout(warmPages, 3000); setTimeout(warmChannel, 1800); setTimeout(prebuild, 2500);
      // the launch's own moments, in this order, one at a time once the screen is free; the roster's queue up as it comes
      moment(tgComment); moment(computerHint); booted = true; setTimeout(() => moment(celebrate));
    });
    const tick = setInterval(() => (clock = nowTs()), 30000);

    return () => { clearInterval(tick); removeEventListener('keydown', esc); };
  });
</script>

<main class="app">
  {#each tabs as tab (tab)}
    <section class="tab" class:on={ui.tab === tab} class:drawing={drawing === tab && ui.tab !== tab} aria-hidden={ui.tab !== tab} inert={!!session.banned || gated}>
      {#if tab === 'afisha'}
        {#if built.afisha}<ListPage />{/if}
      {:else if tab === 'forum'}
        {#if built.forum}{#await channelPage() then m}<m.default />{/await}{/if}
      {:else if tab === 'club'}
        {#if built.club}<Clubs />{/if}
      {:else if built.profile}<Me />{/if}
    </section>
  {/each}

  <!-- scrolled content fades under the clock and Telegram's buttons instead of running into them;
       the same glow and background as the pages, so at rest it can't be seen; the feed's posters go full height -->
  <div class="topfade" aria-hidden="true" use:unfeed></div><div class="botfade" aria-hidden="true" use:unfeed></div>
  <div class="cap-theme {capOf?.theme ? `theme-${capOf.theme}` : ''}"><Capsule {live} title={capTitle} icon={capIcon} spin={!!ui.busy} mark={!ui.busy && !!capOf?.mark} tint={capOf?.tint} /></div>
  <Nav {tabs} labels={tabs.map((k) => TAB_LABEL[k]())} dot={tabs.map((k) => TAB_DOT[k]())} />

  {#if gated}{#await consentGate() then m}<m.default />{/await}{/if}
  {#each overlays as o (o.id)}
    {#if shown(o)}<o.component {...o.props} overlay={o} />{/if}
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
  .topfade { position: absolute; inset: 0; z-index: calc(var(--z-capsule) - 1); pointer-events: none; background: color-mix(in srgb, var(--bg) 88%, transparent);
    -webkit-mask-image: linear-gradient(#000 calc(var(--head-bottom) - 4px), transparent var(--page-top));
    mask-image: linear-gradient(#000 calc(var(--head-bottom) - 4px), transparent var(--page-top)); }
  /* and under the bottom bar, softer: the glass still has something to bend (mockup v23) */
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
  .tab { position: absolute; inset: 0; visibility: hidden; z-index: -1; }
  /* where the engine has it, a tab away is skipped whole (no style, layout or paint while it waits; its scroll and
     layout kept): flipping `visibility` restyled every node of the tab on each switch (5k on a full Afisha: 65 ms) */
  @supports (content-visibility: hidden) { .tab { visibility: visible; content-visibility: hidden; } .tab.drawing { content-visibility: visible; opacity: 0; } }
  /* opacity only, backwards fill: a lingering transform fill would pin the pages (prototype bug) */
  .tab.on { visibility: visible; content-visibility: visible; z-index: auto; animation: tabIn 200ms var(--ease) backwards; }
  .view.off { display: none; }
  @keyframes tabIn { from { opacity: 0; } }
</style>
