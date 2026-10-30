// Shared data the screens read, kept in one place per entity so a change shows everywhere at once
// (one home per thing). Actions update optimistically and roll back if the server says no.
import { api, ApiErr, type ClassItem, type EventCard, type Chats, type EventFull, type Friends, type Id, type Org, type PersonCard, type Post, type RegistryOrg, type TeamMember } from '../api';
import { joinClasses } from '../classes';
import { t, type Key, subjectOf } from '../i18n/index.svelte';
import { say } from './ui.svelte';
import { asStudent, loadMe, session } from './session.svelte';
import { sheets } from './sheets';
import { haptic, requestWriteAccess } from '../tg';
import { burst } from '../../ui/burst';
import { SvelteSet } from 'svelte/reactivity';
import { dayNo, nowTs } from '../time';
import { clearCache } from './cache';

export const data = $state({
  events: [] as EventCard[],
  eventsReady: false,
  chats: null as Chats | null, // KBTU's chats for Clubs: loaded with the Afisha, so the row is there before the page opens (B5)
  orgs: [] as Org[],
  schedule: [] as ClassItem[],
  posts: [] as Post[],
  friends: null as Friends | null, // Profile → Friends: loaded as soon as I'm known to be a student, so the page opens full
  myCard: null as PersonCard | null, // my own card (numbers, awards, showcase): Profile's hero and the Awards page, the same way
  news: null as { casts: Post[]; posts: Post[] } | null, // tab 2 → News for club members: broadcasts, then my clubs' posts
  studio: {} as Record<number, EventCard[]>,  // tab 2 → Studio: each of my clubs' events (the one in view comes with the app)
  team: {} as Record<number, TeamMember[]>,   // tab 2 → Team: each of my clubs' people
  registry: null as RegistryOrg[] | null,     // DMP's registry, this month: loaded with the app, never kept on the phone (contacts)
  error: false,
  rev: 0,                  // bumps after a Studio change, so the Studio lists reload
});

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

/** My card (the Profile hero's numbers, the Awards page), in the background like friends. */
export async function loadMyCard(): Promise<void> {
  const me = session.me;
  if (!me?.student) { data.myCard = null; return; }
  try { data.myCard = await api.person(me.id); } catch { /* the last copy stays */ }
}

/** News for a club member (broadcasts, my clubs' and followed clubs' posts), in the background like friends; their photos
 * are fetched ahead. Called again after a post is published, edited or pinned. */
export async function loadNews(): Promise<void> {
  if (!session.me?.student) { data.news = null; return; }
  try { // a follower in no club: no broadcasts (they reach club members), the posts of the clubs followed
    const [casts, posts] = await Promise.all([session.me.memberships.length ? api.posts('clubs') : [], api.posts('subs')]);
    data.news = { casts, posts };
    warm([...casts, ...posts].slice(0, 6).map((p) => p.photo?.url));
  } catch { /* the last copy stays */ }
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
export async function loadRegistry(): Promise<boolean> {
  try { data.registry = await api.registry(0); return true; } catch { return false; }
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

export async function loadAfisha(): Promise<void> {
  loadChats();
  try {
    const [events, orgs, schedule, posts] = await Promise.all([api.events(), api.orgs(), api.schedule(), api.posts('all')]);
    data.events = events; data.orgs = orgs; data.schedule = joinClasses(schedule); data.posts = posts;
    warm(posts.slice(0, 4).map((p) => p.photo?.url)); // Afisha's News page opens with its first photos in place
    data.error = false;
  } catch { data.error = true; }
  data.eventsReady = true;
}

// whose chats we hold: "for you" depends on my school and course, so a new me asks again
export let chatsFor: Id | null | undefined;
export function loadChats(): void {
  chatsFor = session.me?.id ?? null;
  api.chats().then((c) => (data.chats = c)).catch(() => (chatsFor = undefined)); // Clubs asks again
}

/** An event the app holds: the Afisha's, else a club's in Studio (drafts, team-only ones) */
export function eventById(id: Id): EventCard | undefined {
  return data.events.find((e) => e.id === id) ?? Object.values(data.studio).flat().find((e) => e.id === id);
}

// An event's details (the text, album, updates), asked for the moment a finger touches its card: the sheet opens a beat
// later with them on the way or already there. Taken once, so a sheet opened again later asks afresh.
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
  return a && Date.now() - a.at < 10_000 ? a.p : api.event(id);
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
  const i = data.events.findIndex((e) => e.id === card.id);
  if (i >= 0) data.events[i] = card;
}

function errorText(e: unknown): string {
  if (e instanceof ApiErr) {
    if (e.code === 'closed') return e.message === 'deadline' ? t('event.regClosed') : t('event.closed');
    if (e.code === 'full') return t('event.full');
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

/** Going / cancel. Free → going (or waitlist when full); paid → 30-min hold and the payment sheet. */
export function toggleGoing(id: Id, onPaid?: (e: EventCard) => void): void {
  // a guest's "I'm going" finishes by itself after the sign-in, also when the app reopened from Microsoft
  asStudent(async () => {
    const before = eventById(id);
    if (!before || before.status === 'cancelled') return;
    const mine = before.my?.status;
    const leaving = mine === 'going' || mine === 'hold' || mine === 'waitlist';
    // the event needs a phone and none is kept: asked right here, sent with the same tap and kept (PLAN 71)
    const phone = !leaving && before.needsPhone && !session.me?.student?.phone
      ? await sheets.askText({ title: t('pd.ask'), text: t('pd.askText'), ok: t('event.go'), cancel: t('common.cancel'), placeholder: '+7 (707) 123 45 67', max: 18, tel: true })
      : undefined;
    if (phone === null) return;
    // the event's own questions: answered here, sent with the same tap (closed: no sign-up)
    const answers = !leaving && before.form?.length ? await sheets.answers(before.title, before.form) : undefined;
    if (answers === null) return;
    try {
      const after = leaving ? await api.unregister(id) : await api.register(id, refs()[id], phone, answers);
      if (phone && session.me?.student) session.me.student.phone = phone;
      put(after);
      const st = after.my?.status;
      if (leaving) { haptic.warn(); burst(true); say(phrase('say.cancel'), 'crying_face_3d'); }
      else if (st === 'going') { haptic.ok(); burst(false, undefined, after.emoji); say(phrase('say.going'), 'party_popper_3d'); }
      else if (st === 'waitlist') { haptic.tap(); say(phrase('say.wait'), 'pleading_face_3d'); }
      else if (st === 'hold') { haptic.tap(); say(phrase('say.hold'), 'sparkles_3d'); onPaid?.(after); }
      if (!leaving && st !== 'hold') setTimeout(() => void askDm(id), 1300);
    } catch (e) {
      haptic.error();
      say(errorText(e), 'pleading_face_3d');
    }
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
  asStudent(async () => {
    const e = eventById(id); if (!e) return;
    const on = !e.saved;
    e.saved = on; // optimistic
    haptic.tap();
    if (on) burst(false, undefined, e.emoji); // "Save" with a purpose: a moment, and the bot reminds the day before
    try { await api.setSaved(id, on); say(phrase(on ? 'say.save' : 'say.unsave'), on ? 'sparkles_3d' : 'waving_hand_3d_default'); }
    catch { e.saved = !on; say(t('common.error'), 'pleading_face_3d'); }
  });
}

/** Apply to join, or withdraw a pending application after a question (§4.5). The button answers at once. */
export function toggleJoin(id: Id): void {
  asStudent(async () => {
    const o = data.orgs.find((x) => x.id === id); if (!o) return;
    const on = o.myRequest !== 'pending';
    if (!on && !(await sheets.ask({ title: t('join.withdrawAsk'), text: t('join.withdrawText'), ok: t('join.withdraw'), cancel: t('join.keep') }))) return;
    o.myRequest = on ? 'pending' : null;
    haptic.tap();
    try {
      Object.assign(o, await (on ? api.apply(id) : api.withdraw(id)));
      say(phrase(on ? 'say.applied' : 'say.withdrawn'), on ? 'raising_hands_3d_default' : 'waving_hand_3d_default');
    } catch (e) {
      const closed = e instanceof ApiErr && e.code === 'closed';
      o.myRequest = on ? null : 'pending';
      if (closed) o.recruiting = false;
      say(t(closed ? 'join.closed' : 'common.error'), 'pleading_face_3d');
    }
  });
}

export function toggleSub(id: Id): void {
  asStudent(async () => {
    const o = data.orgs.find((x) => x.id === id); if (!o) return;
    const on = !o.subscribed;
    o.subscribed = on; o.subscribers += on ? 1 : -1;
    haptic.tap();
    try { await api.subscribe(id, on); say(phrase(on ? 'say.sub' : 'say.unsub'), on ? 'raising_hands_3d_default' : 'broken_heart_3d'); }
    catch { o.subscribed = !on; o.subscribers += on ? -1 : 1; say(t('common.error'), 'pleading_face_3d'); }
  });
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
    clearCache(); // the phone's saved copy of the app's data held the week for days (privacy review)
    haptic.ok(); say(t('pd.deleted'), 'sparkles_3d');
  } catch {
    // the server's own word, not the week from before: it may have deleted it, or a newer upload may have come
    data.schedule = await api.schedule().catch(() => before);
    haptic.error(); say(t('common.error'), 'pleading_face_3d');
  }
}
