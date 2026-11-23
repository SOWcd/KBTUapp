// Shared data the screens read, kept in one place per entity so a change shows everywhere at once
// (one home per thing). Actions update optimistically and roll back if the server says no.
import { api, ApiErr, type AlbumPhoto, type GalleryAlbum, type GalleryTopic, type AdminStats, type Inbox, type ClassItem, type Membership, type EventCard, type Chats, type Credits, type EventFull, type Friends, type Id, type Org, type PersonCard, type Post, type RegistryOrg, type ChatTree, type StaffMute, type TeamMember, type VolLedger, type Appeal, type SgQueue, type Solved, type TeamPick } from '../api';
import type { MyRegistration, SantaChats } from '../api';
import { joinClasses } from '../classes';
import { teamError } from '../teams';
import { teamConsentOk, TEAM_CONSENT } from '../teamConsent';
import { t, tn, type Key, subjectOf, i18n } from '../i18n/index.svelte';
import { shrink } from '../photo';
import { close, overlays, say } from './ui.svelte';
import { asStudent, loadMe, session } from './session.svelte';
import { staffStill, onStaffLoss } from './staffAccess.svelte';
import { sheets } from './sheets';
import { onTeam } from '../perms';
import { haptic, requestWriteAccess } from '../tg';
import { count } from '../stats';
import { burst } from '../../ui/burst';
import { SvelteSet } from 'svelte/reactivity';
import { dayNo, nowTs } from '../time';
import { clearCache } from './cache';
import { castingOn } from '../posts';

export const data = $state({
  events: [] as EventCard[],
  // events opened outside the afisha (a club's page, a link: an initiative's are only there, server seats.on_afisha),
  // kept for the session so their buttons work; never saved on the phone
  opened: [] as EventCard[],
  eventsReady: false,
  past: [] as EventCard[], // Afisha's "Past": every Afisha event of the last month, mine marked by `my`, newest first (with the Afisha)
  myPast: null as EventCard[] | null, // my recent check-ins, including events outside the Afisha
  credits: null as Credits | null, // the people of the app (server credits.py): with the app, so its row and screen never wait
  chats: null as Chats | null, // KBTU's chats for Clubs: loaded with the Afisha, so the row is there before the page opens (B5)
  gallery: [] as AlbumPhoto[], // the Afisha's Gallery, newest first: the student's first page, with the app (loadGallery)
  galleryAlbums: [] as GalleryAlbum[], // the events' albums on its shelf, the newest first (with the first page)
  galleryPost: null as { events: { id: Id; title: string }[] } | null, // I may post (GALLERY), and to which of my events
  galleryState: 'new' as 'new' | 'ready' | 'failed', // the Gallery's first page: not here yet, here, or the load failed with nothing to show
  galleryPosted: 0, // my posts started (postGallery): the Gallery goes to All and its top, where they land
  orgs: [] as Org[],
  small: [] as Org[], // under the registry's size bar: search alone finds them
  schedule: [] as ClassItem[],
  posts: [] as Post[],
  castings: [] as Post[], // the Clubs tab's "recruiting" strip, read once with the Afisha (currentCastings)
  friends: null as Friends | null, // Profile → Friends: loaded as soon as I'm known to be a student, so the page opens full
  myCard: null as PersonCard | null, // my own card (numbers, awards, showcase): Profile's hero and the Awards page, the same way
  news: null as { casts: Post[]; posts: Post[] } | null, // tab 2 → News for club members: broadcasts, then my clubs' posts
  studio: {} as Record<number, EventCard[]>,  // tab 2 → Studio: each of my clubs' events (the one in view comes with the app)
  team: {} as Record<number, TeamMember[]>,   // tab 2 → Team: each of my clubs' people
  appeals: null as Appeal[] | null,           // my appeals to SG: with the app (APPEALS on), never kept on the phone
  solved: [] as Solved[],                     // "Solved by your appeals": with my appeals, one request
  sg: null as SgQueue | null,                 // SG's queue (its granted people): with the app, never kept on the phone
  asks: null as Appeal[] | null,              // my questions to the help desk (ASK on): with the app, never kept on the phone
  helpq: null as SgQueue | null,              // the help desk's queue (its granted people): with the app, never kept on the phone
  vol: null as VolLedger | null,              // a club's volunteers ledger (its President and whom she grants): with the app, never kept on the phone (contacts)
  registry: null as RegistryOrg[] | null,
  chatTrees: null as ChatTree[] | null,       // DMP's tree of every club's groups (counts only): with the registry     // DMP's registry, this month: loaded with the app, never kept on the phone (contacts)
  inbox: null as Inbox | null,                // the staff's Admin → Inbox: loaded with the app, again each time Admin opens
  adminStats: null as AdminStats | null,      // the admins' Admin → stats card: with the inbox (moderators never see it)
  staffMutes: null as StaffMute[] | null,     // Admin → My notifications: with the inbox's first load, again as the page opens
  staffMutesFailed: false,
  santaChat: {} as Record<number, SantaChats>, // Secret Santa's chat by game: read as its page or a thread opens, never kept on the phone
  error: false,
  rev: 0,                  // bumps after a Studio change, so the Studio lists reload
  kept: 0,                 // bumps after a change inside a list (a tap), so the phone's copy is saved again (App)
});

/** Secret Santa's chat of one game: read again whenever its page or a thread opens (the bot's push leads there); no polling */
export const loadSantaChat = (id: Id): Promise<void> => api.santaChat(id).then((c) => { data.santaChat[id] = c; }).catch(() => {});

/** A friendship changed (a request answered, a QR used): the Friends page and the Profile tab's dot catch up. */
export function friendsChanged(): void { people.clear(); void loadFriends(); void loadMe(); }

/** Friends, requests and where friends go, in the background (the speed rule: the page never waits for it); their faces
 * and the covers of where they go are fetched ahead too, so the page opens complete, not picture by picture. */
export async function loadFriends(): Promise<void> {
  if (!session.me?.student) { data.friends = null; return; }
  try {
    const f = (data.friends = await api.friends());
    warm([...f.incoming, ...f.friends].slice(0, 16).map((r) => r.person.avatar), f.going.slice(0, 6).flatMap((e, i) => [e.cover?.thumb, i < 2 ? e.cover?.url : null]));
  } catch { /* the last copy stays */ }
}

/** The Gallery in the background; its card's photos fetched ahead. all: the pages after the first too (as it opens, so the
 *  viewer swipes across all of it). galleryState says where the first page stands, so the screen can tell "empty" from
 *  "not yet" and "failed". ponytail: up to 600 rows at once, thumbnails lazy; page on scroll if it ever outgrows that. */
export async function loadGallery(all = false): Promise<void> {
  if (!session.me?.student) { data.gallery = []; data.galleryAlbums = []; data.galleryPost = null; return; }
  if (data.galleryState === 'failed') data.galleryState = 'new';
  try {
    let page = await api.gallery();
    data.galleryPost = page.post ?? null;
    data.galleryAlbums = page.albums ?? [];
    const got = [...page.photos];
    while (all && page.more && got.length < 600) { page = await api.gallery(got[got.length - 1].id); got.push(...page.photos); }
    data.gallery = [...data.gallery.filter((p) => p.pending || p.failed), ...got]; // mine still uploading stay on top
    data.galleryState = 'ready';
    warm(got.slice(0, 4).map((p) => p.thumb));
  } catch { if (data.galleryState === 'new') data.galleryState = 'failed'; /* else the last copy stays */ }
}
/** A theme's first page into the same list (the Gallery's filter shows what is here at once; this brings what the
 *  list hasn't reached yet). Newest first stays: a file's id is the order. false: it failed. */
export async function loadGalleryTheme(topic: GalleryTopic | 'events'): Promise<boolean> {
  try {
    const got = (await api.gallery(undefined, topic)).photos, have = new Set(data.gallery.map((p) => p.id));
    const fresh = got.filter((p) => !have.has(p.id)), mine = (p: AlbumPhoto) => p.pending || p.failed;
    if (fresh.length) data.gallery = [...data.gallery.filter(mine), ...[...data.gallery.filter((p) => !mine(p)), ...fresh].sort((a, b) => b.id - a.id)];
    return true;
  } catch { return false; }
}
/** Reported from the Gallery: gone for me at once. */
export const galleryGone = (p: AlbumPhoto): void => { data.gallery = data.gallery.filter((x) => x.id !== p.id); };

/** My photos into the Gallery (to an event's album too): each on top of the grid at once from the phone's own copy, in
 *  its own shape, marked while it uploads (one after another); the server's then takes its tile over (key: the same
 *  element, no flash). A refused one goes, with a toast; one the network dropped stays with Retry and Remove. */
let pendingId = -1;
const waiting = new Map<Id, { file: File; event?: Id; topic?: GalleryTopic }>(); // my uploads not landed yet, by their tile
const size = (url: string) => new Promise<{ w: number; h: number }>((done) => {
  const img = new Image();
  img.onload = () => done({ w: img.naturalWidth, h: img.naturalHeight });
  img.onerror = () => done({ w: 0, h: 0 });
  img.src = url;
});
export async function postGallery(files: File[], event?: Id, topic?: GalleryTopic): Promise<void> {
  const to = data.galleryPost?.events.find((e) => e.id === event); // under its theme at once
  const mine = await Promise.all(files.slice(0, 10).map(async (file) => {
    const url = URL.createObjectURL(file), id = pendingId--;
    waiting.set(id, { file, event, topic });
    return { id, key: id, url, thumb: url, ...(await size(url)), blur: '', canDelete: false, by: session.me?.name ?? null, mine: true, pending: true, ...(to ? { event: to } : { topic }) } satisfies AlbumPhoto;
  }));
  data.gallery = [...[...mine].reverse(), ...data.gallery]; // the last one uploads last: the newest, on top
  data.galleryPosted++;
  let added = 0;
  for (const p of mine) {
    const at = await upload(p);
    if (at === 'ok') added++;
    if (at === 'stop') { drop(mine.filter((x) => waiting.has(x.id) && data.gallery.some((y) => y.id === x.id && y.pending))); break; } // the rest of this batch goes too (the day's limit, the event)
  }
  if (added) { burst(); say(tn('album.added', added), 'camera_with_flash_3d'); }
}
function drop(ps: AlbumPhoto[]): void {
  const ids = new Set(ps.map((p) => p.id));
  for (const p of ps) { waiting.delete(p.id); URL.revokeObjectURL(p.url); }
  data.gallery = data.gallery.filter((x) => !ids.has(x.id));
}
let line: Promise<unknown> = Promise.resolve(); // one upload at a time, a Retry too (the server takes one per person)
const upload = (p: AlbumPhoto) => (line = line.then(() => send(p))) as Promise<'ok' | 'failed' | 'stop' | 'gone'>;
async function send(p: AlbumPhoto): Promise<'ok' | 'failed' | 'stop' | 'gone'> {
  const w = waiting.get(p.id);
  if (!w) return 'gone';
  try {
    const got = await api.postGalleryPhoto(await shrink(w.file), w.event, w.topic);
    await size(got.thumb); // fetched before it takes the tile over: the phone's copy never gives way to a blank
    data.gallery = data.gallery.filter((x) => x.id !== got.id).map((x) => (x.id === p.id ? { ...got, key: p.id } : x));
    waiting.delete(p.id);
    URL.revokeObjectURL(p.url);
    haptic.tap();
    return 'ok';
  } catch (err) {
    haptic.error();
    const code = err instanceof ApiErr ? err.code : '';
    if (!code || code === 'unavailable') { // never reached the server: the photo waits for another try
      data.gallery = data.gallery.map((x) => (x.id === p.id ? { ...x, pending: false, failed: true } : x));
      return 'failed';
    }
    drop([p]);
    say(t(code === 'rate_limited' ? 'gallery.tooMany' : code === 'bad_input' ? 'ed.photoBad' : 'common.error'), 'pleading_face_3d');
    return code === 'rate_limited' || code === 'forbidden' || code === 'not_found' ? 'stop' : 'gone';
  }
}
/** A failed upload again, or out of the grid. */
export async function retryGallery(p: AlbumPhoto): Promise<void> {
  data.gallery = data.gallery.map((x) => (x.id === p.id ? { ...x, pending: true, failed: false } : x));
  if ((await upload(p)) === 'ok') say(tn('album.added', 1), 'camera_with_flash_3d');
}
export const dropGallery = (p: AlbumPhoto): void => drop([p]);
/** My own photo out of the Gallery (and the albums I put it in); null: it stays (the server said no). */
export async function deleteGallery(p: AlbumPhoto): Promise<AlbumPhoto[] | null> {
  try { await api.deleteGalleryPhoto(p.id); galleryGone(p); return data.gallery; }
  catch { haptic.error(); say(t('common.error'), 'warning_3d'); return null; }
}

/** My card (the Profile hero's numbers, the Awards page), in the background like friends. join: a quiet refresh (the
 * app's start, Profile or Awards coming into view) takes the load already on its way, as loadNews does: a launch on
 * Profile asked for the same card three times at once. A refresh after a write never joins: it must see the write. */
let cardLoad: Promise<void> | null = null;
export function loadMyCard(join = false): Promise<void> {
  if (join && cardLoad) return cardLoad;
  const p = (async () => {
    const me = session.me;
    if (!me?.student) { data.myCard = null; return; }
    try { data.myCard = await api.person(me.id); } catch { /* the last copy stays */ }
  })();
  cardLoad = p;
  void p.finally(() => { if (cardLoad === p) cardLoad = null; });
  return p;
}

/** News for a club member (broadcasts, my clubs' and followed clubs' posts), in the background like friends; their photos
 * are fetched ahead. Called again after a post is published, edited or pinned. join: a quiet refresh (the app's start, List
 * coming into view) takes the load already on its way: at a launch both asked, and the feed went twice. A refresh after a
 * write never joins: it must see the write. */
let newsLoad: Promise<void> | null = null;
export function loadNews(join = false): Promise<void> {
  if (join && newsLoad) return newsLoad;
  const p = (async () => {
    if (!session.me?.student) { data.news = null; return; }
    try { // a follower in no club: no broadcasts (they reach club members), the posts of the clubs followed
      const [casts, posts] = await Promise.all([session.me.memberships.length ? api.posts('clubs') : [], api.posts('subs')]);
      data.news = { casts, posts };
      warm([...casts, ...posts].slice(0, 6).map((p) => p.photo?.url));
    } catch { /* the last copy stays */ }
  })();
  newsLoad = p;
  void p.finally(() => { if (newsLoad === p) newsLoad = null; });
  return p;
}

/** A club's events for Studio and its people for Team, kept per club; the club in view loads with the app, the others
 * the first time they're picked; every visit refreshes quietly. */
export async function loadStudio(org: Id): Promise<void> {
  try { data.studio[org] = await api.orgEvents(org); } catch { /* the last copy stays */ }
}
export async function loadTeam(org: Id): Promise<void> {
  try { data.team[org] = await api.team(org); } catch { data.team[org] ??= []; /* the last copy stays; never an endless placeholder */ }
}

/** DMP's registry for this month (the overseers' main page), in the background; false when the server said no. */
/** The ledger is no longer mine to see (access taken back, unlinked, the switch off): the copy goes and every sheet of it closes. */
export function volGone(e: unknown): boolean {
  if (!(e instanceof ApiErr && (e.code === 'forbidden' || e.code === 'not_found'))) return false; // offline: the last copy stays
  data.vol = null;
  for (const o of overlays) if (o.props.vol) close(o.id, false);
  return true;
}

export async function loadAppeals(): Promise<void> {
  try { const r = await api.appeals(); data.appeals = r.items; data.solved = r.solved; } catch { /* offline: the last copy stays */ }
}
export async function loadSg(): Promise<void> {
  try { data.sg = await api.sgQueue(); } catch (e) { if (e instanceof ApiErr && e.code !== 'unavailable') data.sg = null; }
}

export async function loadAsks(): Promise<void> {
  try { data.asks = (await api.myAsks()).items; } catch { /* offline: the last copy stays */ }
}
export async function loadHelpq(): Promise<void> {
  try { data.helpq = await api.helpQueue(); } catch (e) { if (e instanceof ApiErr && e.code !== 'unavailable') data.helpq = null; }
}

export async function loadVol(): Promise<void> {
  try { data.vol = await api.volLedger(); } catch (e) { volGone(e); }
}

export async function loadRegistry(): Promise<boolean> {
  try { data.registry = await api.registry(0); void loadChatTrees(); return true; } catch { return false; }
}
export async function loadChatTrees(): Promise<void> {
  try { data.chatTrees = await api.registryChats(); } catch { /* offline: the last copy stays */ }
}

/** Pictures a page is about to show, into the browser's cache once the app is idle. */
function warm(...lists: (string | null | undefined)[][]): void {
  setTimeout(() => { for (const u of lists.flat()) if (u) { const img = new Image(); img.decoding = 'async'; img.src = u; } }, 300);
}

/** After a Studio change: the public lists and the Studio reload (one home per thing). */
export function studioChanged(): void { data.rev++; void loadAfisha(); }

/** One live phrase in the current language: variants are separated by '|'. */
export function phrase(key: Key, vars?: Record<string, string | number>): string {
  const all = t(key, vars).split('|');
  return all[Math.floor(Math.random() * all.length)];
}

let taps = 0; // a write while the lists reload: the older answer must not undo it on screen (bumped when it starts and when it ends)
let ratingTaps = 0; // ratings and dismissals also update the past lists
let myPastSeq = 0;
/** Runs a write on a list's item; a list asked before it started or finished is older than it. */
async function writing(f: () => Promise<void>): Promise<void> { taps++; try { await f(); } finally { taps++; } }

export async function loadMyPast(): Promise<void> {
  const seq = ++myPastSeq, ratedAt = ratingTaps;
  try {
    const past = await api.attendedEvents();
    if (seq === myPastSeq && ratedAt === ratingTaps) data.myPast = past;
  } catch { /* the last copy stays */ }
}

export async function loadAfisha(): Promise<void> {
  loadChats();
  void loadMyPast();
  try {
    // each list on its own: one failing keeps the others' fresh copies (the last copy of it stays)
    const at = taps, ratedAt = ratingTaps;
    const [events, orgs, schedule, posts, past, castings] = await Promise.allSettled([api.events(), api.orgs(), api.schedule(), api.posts('all'), api.pastEvents(), api.castings()]);
    if (castings.status === 'fulfilled') data.castings = castings.value;
    if (past.status === 'fulfilled' && ratedAt === ratingTaps) data.past = past.value;
    if (events.status === 'fulfilled' && at === taps) data.events = events.value;
    if (orgs.status === 'fulfilled' && at === taps) { data.orgs = orgs.value.filter((o) => !o.small); data.small = orgs.value.filter((o) => o.small); }
    if (schedule.status === 'fulfilled') data.schedule = joinClasses(schedule.value);
    if (posts.status === 'fulfilled') { data.posts = posts.value; warm(posts.value.slice(0, 4).map((p) => p.photo?.url)); } // News opens with its first photos
    data.error = events.status === 'rejected';
  } catch { data.error = true; }
  data.eventsReady = true;
}

/** Castings not over yet, soonest first (the server's order; the phone's clock drops what ended since). */
export const currentCastings = (now = nowTs()): Post[] => data.castings.filter((p) => p.casting && castingOn(p.casting, now));
export async function loadCastings(): Promise<void> {
  try { data.castings = await api.castings(); } catch { /* the last copy stays */ }
}

/** The club calls a casting off, after a question: marked at once, back if the server says no; the post stays. */
export async function cancelCasting(p: Post): Promise<void> {
  const c = p.casting;
  if (!c || !(await sheets.ask({ title: t('casting.cancelAsk'), text: t('casting.cancelText'), ok: t('casting.cancel'), cancel: t('casting.keep'), danger: true }))) return;
  const strip = data.castings;
  c.cancelled = true; data.castings = strip.filter((x) => x.id !== p.id);
  haptic.warn();
  try {
    Object.assign(p, await api.cancelCasting(p.id)); // now it can also be deleted
    say(t('casting.cancelSay'), 'waving_hand_3d_default');
    void loadNews(); api.posts('all').then((l) => (data.posts = l)).catch(() => {}); // the other lists hold their own copies
  } catch { c.cancelled = false; data.castings = strip; haptic.error(); say(t('common.error'), 'warning_3d'); }
}

/** Admin → Inbox and Done, the staff's (one request); the shield's number catches up with it. withStats: the admin's
 *  numbers too (the app's start and Admin opening; not after each decision) */
export async function loadInbox(withStats = false): Promise<void> {
  if (session.me?.role !== 'admin' && session.me?.role !== 'moderator') { data.inbox = null; return; }
  const admin = staffStill('admin'), staff = staffStill('staff'); // an answer after the role went is not kept
  if (withStats && session.me.role === 'admin') api.adminStats().then((s) => { if (admin()) data.adminStats = s; }).catch(() => {});
  if (withStats && !data.staffMutes) loadStaffMutes();
  try {
    const inbox = await api.inbox();
    if (!staff()) return;
    data.inbox = inbox;
    const n = decisions(inbox);
    if (session.me && session.me.counters.inbox !== n) session.me.counters.inbox = n;
  } catch { /* the list keeps what it had */ }
}

/** The badge's number: real decisions only; a channel's draft (autoev) waits in its club's Studio, nobody's call (server inbox.count) */
export const decisions = (i: Inbox | null): number => i?.items.filter((x) => x.kind !== 'autoev').length ?? 0;

/** Admin → My notifications, staff only; a failure keeps what it had (the page offers a retry when it has nothing).
 *  An answer asked before a tap (mutedTap) is older than the switch: dropped. */
onStaffLoss((has) => {
  if (!has('admin')) data.adminStats = null;
  if (!has('staff')) { data.inbox = null; data.staffMutes = null; }
  else if (!has('admin')) { data.inbox = null; void loadInbox(); } // a moderator's queue, without the admin's cards
});
let muteTaps = 0;
export const mutedTap = () => void muteTaps++;
export function loadStaffMutes(): void {
  if (session.me?.role !== 'admin' && session.me?.role !== 'moderator') return;
  const at = muteTaps, staff = staffStill('staff');
  data.staffMutesFailed = false;
  api.staffMutes().then((l) => { if (muteTaps === at && staff()) data.staffMutes = l; }).catch(() => (data.staffMutesFailed = !data.staffMutes));
}

/** The people of the app. One read in flight for everyone who asks (the app's start, the bot's link, the screen); who is
 *  named changes with a person's own answer, so it is read again when the screen opens and when the app comes back
 *  (`fresh`: a copy this young will do). A reply that something newer has overtaken (a later read, my own answer) is
 *  dropped, and so is every reply while my answer is on its way: it may show me as I was. */
let creditsSeq = 0, creditsAt = 0, creditsPuts = 0, creditsFlight: Promise<void> | null = null;
export function loadCredits(fresh = 0): Promise<void> {
  if (creditsFlight) return creditsFlight;
  if (fresh && data.credits && Date.now() - creditsAt < fresh) return Promise.resolve();
  const n = ++creditsSeq;
  const flight = api.credits().then((c) => { if (n === creditsSeq && !creditsPuts) { data.credits = c; creditsAt = Date.now(); } }, () => {})
    .finally(() => { if (creditsFlight === flight) creditsFlight = null; });
  return (creditsFlight = flight);
}
/** Around my own answer (lib/credits.ts): `sending` as it leaves and again when it has settled. Each cuts off every
 *  read already on its way (older than my answer, or as old); once nothing of mine is pending the list is read anew,
 *  the only thing painted: the answer's own reply never is (a read may be newer than it). */
export function creditsAnswer(sending: boolean): Promise<void> {
  creditsSeq++; creditsFlight = null; creditsAt = 0;
  creditsPuts += sending ? 1 : -1;
  return sending || creditsPuts ? Promise.resolve() : loadCredits();
}

// whose chats we hold: "for you" depends on my school and course, so a new me asks again
export let chatsFor: Id | null | undefined;
export function loadChats(): void {
  chatsFor = session.me?.id ?? null;
  api.chats().then((c) => (data.chats = c)).catch(() => (chatsFor = undefined)); // Clubs asks again
}

/** An event the app holds: the Afisha's, else a club's in Studio (drafts, team-only ones) */
export function eventById(id: Id): EventCard | undefined {
  return data.events.find((e) => e.id === id) ?? Object.values(data.studio).flat().find((e) => e.id === id)
    ?? data.opened.find((e) => e.id === id) ?? data.past.find((e) => e.id === id);
}
function keepOpened(d: EventFull): EventFull { if (!eventById(d.id)) data.opened.push(d); return d; }
/** The app's card, or the server's for one it doesn't hold yet (kept: opened) */
export const cardFor = async (id: Id): Promise<EventCard | undefined> => eventById(id) ?? eventDetails(id).then(() => eventById(id), () => undefined);

// An event's details (the text, album, updates), asked for as a finger touches its card (lib/touch.ts: not for a flick
// that only starts on it): the sheet opens a beat later with them on the way or already there. Taken once, so a sheet opened again later asks afresh.
const ahead = new Map<Id, { at: number; p: Promise<EventFull> }>();
export function prefetchEvent(id: Id): void {
  const a = ahead.get(id);
  if (a && Date.now() - a.at < 10_000) return;
  const p = api.event(id);
  p.catch(() => ahead.delete(id));
  ahead.set(id, { at: Date.now(), p });
}
export function eventDetails(id: Id): Promise<EventFull> {
  const a = ahead.get(id);
  ahead.delete(id);
  return (a && Date.now() - a.at < 10_000 ? a.p : api.event(id)).then(keepOpened);
}

// a person's card, fetched from the touch (B4: the card opened as a plain one, then jumped into its skin) and kept for
// the session, so a second look opens whole at once while it refreshes
const people = new Map<Id, { at: number; p: Promise<PersonCard>; card?: PersonCard }>();
export function prefetchPerson(id: Id): void {
  const a = people.get(id);
  if (a && Date.now() - a.at < 10_000) return;
  const e: { at: number; p: Promise<PersonCard>; card?: PersonCard } = { at: Date.now(), p: api.person(id), card: a?.card };
  e.p.then((c) => (e.card = c), () => (e.at = 0));
  people.set(id, e);
}
export function personCard(id: Id): { p: Promise<PersonCard>; card?: PersonCard } {
  prefetchPerson(id);
  return people.get(id)!;
}
// a card after a friend action (or its stranger view when refused) replaces the old fetch whole: a reopen within 10 s
// brought the old one back (an unfriended person with their friends-only data)
export function keepPerson(c: PersonCard): void { people.set(c.id, { at: Date.now(), p: Promise.resolve(c), card: c }); }
export function forgetPeople(): void { people.clear(); }

export function put(card: EventCard): void {
  data.kept++; taps++; // a list asked before this card is older than it
  for (const list of [data.events, data.opened]) {
    const i = list.findIndex((e) => e.id === card.id);
    if (i >= 0) list[i] = card;
  }
}

export const ratingBusy = new SvelteSet<Id>();

export function canAskRating(e: EventCard, now = nowTs()): boolean {
  const end = e.endsAt ?? e.startsAt + 3 * 3600;
  return e.status === 'published' && e.my?.checkedInAt != null && e.my.rating == null && !e.my.ratingDismissed
    && end <= now && now <= end + 7 * 86400;
}

function ratingWritten(id: Id, patch: Partial<Pick<MyRegistration, 'rating' | 'ratingDismissed'>>): void {
  taps++; ratingTaps++;
  ahead.delete(id);
  for (const list of [data.events, data.past, data.myPast ?? [], data.opened]) {
    const my = list.find((e) => e.id === id)?.my;
    if (my) Object.assign(my, patch);
  }
}

export async function saveEventRating(id: Id, score: number, comment?: string): Promise<EventFull | undefined> {
  if (ratingBusy.has(id)) return;
  ratingBusy.add(id);
  try {
    const fresh = await api.rate(id, score, comment);
    ratingWritten(id, { rating: fresh.myRating });
    return fresh;
  } finally { ratingBusy.delete(id); }
}

export async function rateFromPrompt(id: Id, score: number): Promise<void> {
  haptic.select();
  try {
    if (await saveEventRating(id, score)) {
      haptic.ok(); burst(); say(t('rate.thanks'), 'sparkles_3d');
    }
  } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
}

export async function dismissEventRating(id: Id): Promise<void> {
  if (ratingBusy.has(id)) return;
  ratingBusy.add(id);
  haptic.tap();
  try {
    await api.dismissRating(id);
    ratingWritten(id, { ratingDismissed: true });
  } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  finally { ratingBusy.delete(id); }
}

export function errorText(e: unknown): string {
  if (e instanceof ApiErr) {
    const team = teamError(e.code, e.message);  // first: a team's "full" or "closed" is its own (server evteams.py)
    if (e.message === 'team_consent' && e.code === 'forbidden' && session.me?.teams) session.me.teams.consent = false; // the next tap asks
    if (team) return t(team);
    if (e.code === 'closed') return e.message === 'deadline' ? t('event.regClosed') : t('event.closed');
    if (e.code === 'full') return t('event.full');
    if (e.code === 'guest_list') return t('event.guestList'); // tickets only from the organizers' list
    if (e.code === 'forbidden' && e.message === 'team') return t('event.team');
    if (e.code === 'conflict' && e.message === 'answers') { void loadAfisha(); return t('qs.changed'); } // the questions changed meanwhile
  }
  return t('common.error');
}

/** A club member's link to an event (ev_<id>_<code>, "My link"): the code is kept on the phone, so a guest's sign-in
 *  in between doesn't lose it, and goes with the sign-up; the first link opened wins (the server keeps the first too) */
const REF_KEY = 'kb-ref';
const refs = (): Record<string, string> => { try { return JSON.parse(localStorage.getItem(REF_KEY) || '{}'); } catch { return {}; } };
export function keepRef(id: Id, code: string): void {
  const all = refs();
  if (!all[id]) try { localStorage.setItem(REF_KEY, JSON.stringify({ ...all, [id]: code })); } catch { /* blocked */ }
}

/** Events whose Going waits for the server (paid, full, a form): their buttons show a spinner. */
export const goingBusy = new SvelteSet<Id>();
const flying = new Set<Id>();

/** Going / cancel. Free → going (or waitlist when full); paid → 30-min hold and the payment sheet. */
/** team: a team event's way in (create, join by its link, 'solo'); left out, the app asks (sheets.teamPick) */
export function toggleGoing(id: Id, onPaid?: (e: EventCard) => void, team?: TeamPick | 'solo'): void {
  // a guest's "I'm going" finishes by itself after the sign-in, also when the app reopened from Microsoft
  asStudent(async () => {
    const before = await cardFor(id);
    if (!before || before.status === 'cancelled') return;
    const mine = before.my?.status;
    const leaving = mine === 'going' || mine === 'hold' || mine === 'waitlist';
    if (!leaving && onTeam(before, session.me?.memberships)) { haptic.tap(); say(t('event.team'), 'raising_hands_3d_default'); return; }
    // a team event's sign-up is its teams consent: one who hasn't agreed (or took it back) is asked
    // first, every way in; a no signs nobody up. The waitlist isn't a sign-up yet: asked when it is a ticket.
    const fullNow = before.seats != null && before.taken >= before.seats;
    const agrees = !leaving && !!before.teamMax && !fullNow && !session.me?.teams?.consent;
    if (agrees && !(await sheets.ask({ title: t('tm.consentT'), text: t('tm.signupText'), ok: t('tm.signupOk'), cancel: t('common.cancel'),
      link: { label: t('tm.consentLink'), url: `${location.origin}/privacy?lang=${i18n.lang}` } }))) return;
    // the event needs a phone and none is kept: asked right here, sent with the same tap and kept (PLAN 71)
    const phone = !leaving && before.needsPhone && !session.me?.student?.phone
      ? await sheets.askText({ title: t('pd.ask'), text: t('pd.askText'), ok: t('event.go'), cancel: t('common.cancel'), placeholder: '+7 (707) 123 45 67', max: 18, tel: true })
      : undefined;
    if (phone === null) return;
    // the event's own questions: answered here, sent with the same tap (closed: no sign-up)
    const answers = !leaving && before.form?.length ? await sheets.answers(before.title, before.form) : undefined;
    if (answers === null) return;
    // Secret Santa (server santa.py): the wishlist, with the line that says who will see it (the feature's own consent)
    const wish = !leaving && before.santa
      ? await sheets.askText({ title: t('santa.title'), text: t('santa.askText'), ok: t('santa.join'), cancel: t('common.cancel'), placeholder: t('santa.wishPh'), max: 300 })
      : undefined;
    if (wish === null) return;
    // a team event (server evteams.py): make a team, or "I have no team"; a link's join came with the tap. A paid one
    // asks nothing: the captain pays first and makes the team after the receipt (the sheet's "Create team")
    const pick = !leaving && before.teamMax ? team ?? (before.price || fullNow ? undefined : await sheets.teamPick(before.title, before.teamMin ?? 2, before.teamMax)) : undefined;
    if (pick === null) return;
    if (pick && !agrees && !(await teamConsentOk())) return; // the teams' own consent, asked once: a no leaves me not signed up
    const joins = pick && pick !== 'solo' ? pick : undefined;
    if (flying.has(id)) return; // a second tap while the first is on its way
    flying.add(id);
    // a free event with nothing to ask and a seat left: going at once (the speed rule), the server's card settles it;
    // anything else (paid, full, a form) shows the button pressed until the answer
    const sure = !leaving && !before.price && !answers && !phone && !wish && !joins && (before.seats == null || before.taken < before.seats);
    const was = { my: before.my, taken: before.taken };
    if (sure) {
      before.my = { ...(before.my ?? { cancelReason: null, ticketCode: null, holdUntil: null, checkedInAt: null, receipt: 'none' }), status: 'going' };
      before.taken++;
      haptic.tap();
    } else goingBusy.add(id);
    taps++;
    try {
      const after = leaving ? await api.unregister(id) : await api.register(id, refs()[id], phone, answers, joins, wish, agrees ? TEAM_CONSENT : undefined);
      if (!leaving) count('do.signup');
      if (phone && session.me?.student) session.me.student.phone = phone;
      if (after.teamsConsent !== undefined && session.me?.teams) session.me.teams.consent = after.teamsConsent; // the server's word
      put(after);
      const st = after.my?.status;
      if (leaving) { haptic.warn(); burst(true); say(phrase('say.cancel'), 'crying_face_3d'); }
      else if (st === 'going') { if (!sure) haptic.ok(); burst(false, undefined, after.emoji); say(phrase('say.going'), 'party_popper_3d'); }
      else if (st === 'waitlist') { haptic.tap(); say(phrase('say.wait'), 'pleading_face_3d'); }
      else if (st === 'hold') { haptic.tap(); say(phrase('say.hold'), 'sparkles_3d'); onPaid?.(after); }
      if (!leaving && st !== 'hold') setTimeout(() => void askDm(id), 1300);
    } catch (e) {
      if (sure) { before.my = was.my; before.taken = was.taken; }
      haptic.error();
      say(errorText(e), 'pleading_face_3d');
    } finally { goingBusy.delete(id); flying.delete(id); taps++; }
  }, 'go_' + id);
}

/** The bot can't write to someone who never opened it: Telegram's own "allow messages", asked when it pays off (just
 *  signed up), and the server knows at once and sends this event's confirmation. Asked once by itself;
 *  the ticket's "Turn on reminders" asks again. */
export async function askDm(eid?: Id, again = false): Promise<void> {
  if (!session.me || session.me.canDm) return;
  try { if (!again && localStorage.getItem('kb-dm-asked')) return; localStorage.setItem('kb-dm-asked', '1'); } catch { /* blocked */ }
  say(t('dm.why'), 'speech_balloon_3d');
  if (!(await requestWriteAccess())) return;
  try { session.me = await api.dmOn(eid); haptic.ok(); say(t('dm.on'), 'speech_balloon_3d'); } catch { /* the next launch tells the server */ }
}

/** A leaders meeting (§4.10): "Can't make it" — the answer DMP sees; "I'll be there" is toggleGoing. */
export function declineInvite(id: Id, note?: string): void {
  asStudent(async () => {
    try { put(await api.decline(id, note)); haptic.soft(); say(t('lead.declined'), 'waving_hand_3d_default'); }
    catch (e) { haptic.error(); say(errorText(e), 'pleading_face_3d'); }
  });
}

export function toggleSaved(id: Id): void {
  asStudent(() => writing(async () => {
    const e = await cardFor(id); if (!e) return;
    const on = !e.saved;
    e.saved = on; // optimistic
    haptic.tap();
    if (on) burst(false, undefined, e.emoji); // "Save" with a purpose: a moment, and the bot reminds the day before
    try { await api.setSaved(id, on); data.kept++; say(phrase(on ? 'say.save' : 'say.unsave'), on ? 'sparkles_3d' : 'waving_hand_3d_default'); }
    catch { e.saved = !on; say(t('common.error'), 'warning_3d'); }
  }));
}

/** Apply to join, or withdraw a pending application after a question (§4.5). The button answers at once. */
export function toggleJoin(id: Id): void {
  asStudent(() => writing(async () => {
    const o = [...data.orgs, ...data.small].find((x) => x.id === id); if (!o) return;
    const on = o.myRequest !== 'pending';
    if (on && o.joinQuestions?.length) { sheets.joinApply(id); return; } // the club's own questions first
    // the only way in without a form of its own, and it pings the club's president: one question (a president's report)
    if (on && !(await sheets.ask({ title: t('join.applyAsk', { name: o.name }), ok: t('join.apply'), cancel: t('common.cancel') }))) return;
    if (!on && !(await sheets.ask({ title: t('join.withdrawAsk'), text: t('join.withdrawText'), ok: t('join.withdraw'), cancel: t('join.keep') }))) return;
    o.myRequest = on ? 'pending' : null;
    haptic.tap();
    try {
      Object.assign(o, await (on ? api.apply(id) : api.withdraw(id))); data.kept++;
      say(phrase(on ? 'say.applied' : 'say.withdrawn'), on ? 'raising_hands_3d_default' : 'waving_hand_3d_default');
    } catch (e) {
      const closed = e instanceof ApiErr && e.code === 'closed';
      o.myRequest = on ? null : 'pending';
      if (closed) o.recruiting = false;
      say(t(closed ? 'join.closed' : 'common.error'), 'pleading_face_3d');
    }
  }));
}

export function toggleSub(id: Id): void {
  asStudent(() => writing(async () => {
    const o = [...data.orgs, ...data.small].find((x) => x.id === id); if (!o) return;
    const on = !o.subscribed;
    o.subscribed = on; o.subscribers += on ? 1 : -1;
    haptic.tap();
    try { await api.subscribe(id, on); data.kept++; if (on) count('do.follow'); say(phrase(on ? 'say.sub' : 'say.unsub'), on ? 'raising_hands_3d_default' : 'broken_heart_3d'); }
    catch { o.subscribed = !on; o.subscribers += on ? -1 : 1; say(t('common.error'), 'warning_3d'); }
  }));
}

/** Leaving a club from the Clubs tab, what Team's Leave does: one confirm, then gone at once, back if the server says no. */
export async function leaveClub(m: Membership): Promise<void> {
  if (!(await sheets.ask({ title: t('team.leaveAsk', { club: m.org.name }), text: t('team.leaveText'), ok: t('team.leave'), cancel: t('common.cancel'), danger: true }))) return;
  const me = session.me; if (!me) return;
  me.memberships = me.memberships.filter((x) => x.org.id !== m.org.id);
  try { await api.removeMember(m.org.id, me.id); haptic.ok(); say(t('team.left'), 'waving_hand_3d_default'); studioChanged(); void loadMe(); }
  catch (e) {
    me.memberships = [...me.memberships, m];
    haptic.error(); say(e instanceof ApiErr && e.message === 'president' ? t('team.presLeave') : t('common.error'), 'warning_3d');
  }
}

// ---- classes I won't go to: one
// class on one day, kept on this phone (the portal's timetable stays as it is); past days are dropped ----
const SKIP_KEY = 'kb-skip';
/** a class on a day (the local day number): the same subject at the same time is the same class */
export const classKey = (day: number, c: ClassItem): string => `${day}|${c.begins}|${c.subject}`;
export const skipped = new SvelteSet<string>((() => {
  try { return (JSON.parse(localStorage.getItem(SKIP_KEY) || '[]') as string[]).filter((k) => Number(k.split('|')[0]) >= dayNo(nowTs())); }
  catch { return []; }
})());
export async function skipClass(key: string, c: ClassItem): Promise<void> {
  if (skipped.has(key)) { skipped.delete(key); haptic.tap(); say(t('skip.back'), 'sparkles_3d'); }
  else {
    if (!(await sheets.ask({ title: t('skip.ask', { subject: subjectOf(c) }), text: t('skip.text'), ok: t('skip.ok'), cancel: t('skip.cancel') }))) return;
    skipped.add(key); haptic.select(); say(t('skip.done'), 'spiral_calendar_3d');
  }
  try { localStorage.setItem(SKIP_KEY, JSON.stringify([...skipped])); } catch { /* blocked */ }
}

/** My week deleted (the Week sheet): gone from every screen at once, back if the server says no; the classes I skip
 *  go too once it's done (unseen without the week) */
export async function dropSchedule(): Promise<void> {
  const before = data.schedule;
  data.schedule = [];
  try {
    await api.deleteSchedule();
    skipped.clear();
    try { localStorage.removeItem(SKIP_KEY); } catch { /* blocked */ }
    clearCache(); // else the phone's saved copy of the app's data holds the week for days
    haptic.ok(); say(t('pd.deleted'), 'sparkles_3d');
  } catch {
    // the server's own word, not the week from before: it may have deleted it, or a newer upload may have come
    data.schedule = await api.schedule().then(joinClasses).catch(() => before);
    haptic.error(); say(t('common.error'), 'warning_3d');
  }
}
