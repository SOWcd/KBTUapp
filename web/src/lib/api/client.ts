// The real server (SPEC §6). Every call carries Telegram's signed initData; errors come back as
// { error, message } and become ApiErr.
import type { ApiError, ClubApplication, Id, OfficialPath, PersonCard, Video, AdminOrg, AdminEvent, OrgRole, TeamMember, Member, TeamSetup, MemberPatch, Friends, Friendship, FoundStudent, LinkCard, PersonRef, Media, GalleryPage, GalleryTopic, AlbumPhoto, Attendee, DoorPerson, EventUpdate, PostInput, CheckinResult, ClassItem, JoinRequest, CohostInvite, CrewKind, CrewMember, EventReport, ReportMark, ReportPatch, EventCard, EventFull, EventInput, Me, Org, Post, Settings, Ts, FriendInvite, CommentThread, ReportReason, ReportItem, RegistryOrg, SentMemo, RosterMember, RegistryHit, Chat, ChatSection, Chats, ClubApplicationInput, OfficialRequest, LeadersAnswer, MeetingAnswer, OrgPatch, PostPatch, OrgRef, TakenDown, Staff, StaffRow, AuditRow, PlatformRole, Right, MemoDraft, MemoSign, GrantItem, AdminStats, AdminDay, AdminAi, Round, RoundInput, RoundApp, AppStage, RoundSlot, VolunteerApp, TeamAsk, TeamPick, TeamInvite, TeamsBoard, ShortLink, StudioChat, WaitingChat, SwearRow, ChatRoles, RosterRequest, Skill, ForumMe, ForumCard, Ask, AskInput, Contact, ForumMod, AssistReply, Fixable, TgComment, TgcRule, VolLedger, VolPerson, VolDoor, Appeal, AppealHelp, AppealTopic, AppealStatus, SgQueue, Solved } from './types';
import type { Graph } from '../route';
import { splitVariants } from '../awards';
import { ApiErr } from './errors';
import { sheets } from '../state/sheets';
import { tg } from '../tg';
import { i18n } from '../i18n/index.svelte';

// the start's first answers, asked for by index.html with the page: each taken once, in the first seconds, and only when
// signed with the initData this app holds (else the call goes out as usual)
type First = { auth: string; at: number; r: Record<string, Promise<Response> | undefined> };
function first(path: string): Promise<Response> | undefined {
  const f = (window as { __kbFirst?: First }).__kbFirst, p = f?.r[path];
  if (!f || !p) return undefined;
  delete f.r[path];
  return f.auth === tg.initData && Date.now() - f.at < 20_000 ? p : undefined;
}

/** Events the admin opened from Admin: their own routes go as their organizers' (server app.viewer, X-Staff-Event),
 *  each write in the owner's log. Only Admin adds to it. */
export const staffEvents = new Set<Id>();
/** Admin → "an event for a club": while that editor is open, the new event and its cover go as the admin's for this club
 *  (server app.viewer, X-Staff-Org: those routes alone; a video the creator's alone). Only that editor sets it. */
export const staffOrg = { id: 0 as Id };
const staffOf = (method: string, path: string): Record<string, string> => {
  if (staffOrg.id && method === 'POST' && (path === '/photos' || path === '/videos' || path === `/orgs/${staffOrg.id}/events` || path === `/orgs/${staffOrg.id}/events/fill`)) return { 'X-Staff-Org': String(staffOrg.id) };
  const id = /^\/events\/(\d+)(?:[/?]|$)/.exec(path)?.[1];
  return id && staffEvents.has(+id) ? { 'X-Staff-Event': id } : {};
};

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let r: Response;
  const raw = body instanceof Blob; // a file goes as the body itself (POST /api/photos)
  try {
    r = await ((method === 'GET' && body === undefined && first(path)) || fetch('/api' + path, {
      method,
      headers: { Authorization: `tma ${tg.initData}`, ...staffOf(method, path), ...(body === undefined ? {} : { 'Content-Type': raw ? body.type || 'application/octet-stream' : 'application/json' }) },
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    }));
  } catch {
    throw new ApiErr('unavailable', 'network');
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  // banned mid-session: the app hears it from any call, not only at launch
  if (r.status === 403 && (data as ApiError | null)?.message === 'banned') dispatchEvent(new CustomEvent('kb:banned', { detail: data }));
  // held for the policy in force: the gate asks now, in place (App: sheets.consent), never on opening the app
  if (!r.ok && (data as ApiError | null)?.error === 'forbidden' && (data as ApiError | null)?.message === 'consent') sheets.consent();
  if (!r.ok) throw new ApiErr((data as ApiError | null)?.error ?? 'unavailable', (data as ApiError | null)?.message || undefined, (data as Record<string, unknown> | null) ?? {});
  return localize(data) as T;
}

// what the server has in the viewer's language (PLAN 9): a school's name, description and short name (kbtu.edu.kz), a
// club's description and an event's title and description (ai.py). The text as typed stays in `orig`, so a second pass
// (another language, a copy from the cache) starts from it and the editors save it, never a translation.
const SHOWN = ['name', 'realName', 'title', 'description', 'body'] as const; // body: a channel's post (PLAN 86); realName: a person's Latin short name
export function localize(x: unknown): unknown {
  if (Array.isArray(x)) x.forEach(localize);
  else if (x && typeof x === 'object') {
    const o = x as Record<string, unknown>;
    if (o.i18n && typeof o.i18n === 'object') {
      const orig = (o.orig ??= Object.fromEntries(SHOWN.filter((k) => typeof o[k] === 'string').map((k) => [k, o[k]]))) as Record<string, string>;
      const tr = (o.i18n as Record<string, Record<string, string> | undefined>)[i18n.lang] ?? {};
      for (const k of SHOWN) if (k in orig) o[k] = tr[k] || orig[k];
      if (tr.abbr) o.abbr = tr.abbr;
    }
    for (const [k, v] of Object.entries(o)) if (k !== 'orig' && k !== 'i18n' && v && typeof v === 'object') localize(v);
  }
  return x;
}

/** The object as its author typed it (an editor's starting point). */
export const original = <T extends object>(x: T): T => ({ ...x, ...((x as { orig?: object }).orig ?? {}) });

/** Whether the viewer sees this field translated by AI (the "Show original" line). */
export const translated = (x: { orig?: Record<string, string>; title?: string; description?: string | null }, k: 'title' | 'description'): boolean =>
  !!x.orig && typeof x.orig[k] === 'string' && x[k] !== x.orig[k];

const query = (q: Record<string, number | string | undefined>) => {
  const s = Object.entries(q).filter(([, v]) => v != null).map(([k, v]) => `${k}=${encodeURIComponent(v!)}`).join('&');
  return s ? '?' + s : '';
};

// an event's video in 8 MB pieces (Cloudflare refuses a request over 100 MB; a dropped connection resends one piece):
// a piece whose answer got lost is answered with where the file stands, and the next one starts there
const PIECE = 8 * 1024 * 1024;
async function uploadVideo(file: Blob, progress: (done: number) => void, wide = false): Promise<Video> {
  const { id } = await call<{ id: Id }>('POST', '/videos', wide ? { size: file.size, wide } : { size: file.size });
  let at = 0, fails = 0;
  while (at < file.size) {
    try {
      at = (await call<{ at: number }>('PUT', `/videos/${id}?at=${at}`, file.slice(at, at + PIECE))).at;
      fails = 0;
      progress(at / file.size);
    } catch (x) {
      // the network: wait and send it again (the phone may have locked or switched networks); anything else is final
      if (!(x instanceof ApiErr && x.code === 'unavailable') || ++fails > 6) throw x;
      await new Promise((r) => setTimeout(r, 1500 * fails));
    }
  }
  return call('POST', `/videos/${id}/done`);
}

export const server = {
  me: (): Promise<Me> => call('GET', '/me'),
  msStart: (): Promise<{ url: string }> => call('POST', '/ms/start'), // the KBTU Microsoft sign-in link, opened outside Telegram
  msClaim: (claim: string): Promise<{ ok: true }> => call('POST', '/ms/claim', { claim }), // back from /ms.html (startapp=ms_<claim>): only the Telegram that started it takes it
  manualLogin: (i: { firstName: string; lastName: string; studentId: string; course: number }, consentVersion: string): Promise<Me> => call('POST', '/kbtu/manual', { ...i, consentVersion }), // only while it isn't
  updateMe: (patch: Partial<Settings> & { bio?: string; showcase?: string[]; nick?: string | null; avatarTg?: boolean; skin?: Id | 'sower' | null; frame?: string | null; phone?: string | null; school?: string | null; course?: number; city?: string | null; cityHidden?: boolean }
    & { [k in Exclude<Fixable, 'course' | 'school'>]?: string }): Promise<Me> => call('PATCH', '/me', patch), // phone, city: null deletes it; a Fixable: once each (the server says `fixed` after)
  uploadMyPhoto: (file: Blob): Promise<Me> => call('POST', '/me/photo', file), // my own photo: "Photo from Telegram" goes off
  deleteMyPhoto: (): Promise<Me> => call('DELETE', '/me/photo'), // gone from the server too; Telegram's is back
  /** §4.8, with the KBTU login and password again; a wrong or another student's one: bad_input/'credentials';
   *  a President: conflict/'president'. */
  deleteMe: (photos: boolean = false): Promise<Me> => call('POST', '/me/delete', { photos }), // in 7 days (Me.deleteAt); photos: my album photos go too
  deleteInfo: (): Promise<{ photos: number; paid: boolean }> => call('GET', '/me/delete'), // what the delete sheet says first
  consent: (version: string): Promise<Me> => call('POST', '/me/consent', { version }), // agree to a new policy version
  keepMe: (): Promise<Me> => call('POST', '/me/keep'),
  starsInvoice: (amount: number): Promise<{ url: string }> => call('POST', '/donate/stars', { amount }), // Support the app in Telegram Stars: a link for openInvoice
  dmOn: (event?: Id): Promise<Me> => call('POST', '/me/dm', { event }),

  events: (q: { from?: Ts; to?: Ts; org?: Id } = {}): Promise<EventCard[]> => call('GET', '/events' + query({ from: q.from, to: q.to, org: q.org })),
  gallery: (before?: Id, topic?: GalleryTopic | 'events'): Promise<GalleryPage> => call('GET', '/gallery' + query({ before, topic })), // every photo I may see, newest first (students; before: the last id I have); topic: only photos of no event about it; 'events': only the albums
  postGalleryPhoto: (file: Blob, event?: Id, topic?: GalleryTopic): Promise<AlbumPhoto> => call('POST', '/gallery' + query({ event, topic }), file), // into the Gallery under my name (GalleryPage.post); event: its album too; topic: of no event (one of the two, never both)
  deleteGalleryPhoto: (id: Id): Promise<void> => call('DELETE', `/gallery/${id}`), // mine: from the Gallery and the albums I put it in
  pastEvents: (org?: Id, mine?: boolean): Promise<EventCard[]> => call('GET', '/events/past' + query({ org, mine: mine ? 1 : undefined })), // org: a club's latest few; mine: the ones I was signed up for or came to
  event: (id: Id): Promise<EventFull> => call('GET', `/events/${id}`),
  addSeats: (id: Id, add: number): Promise<EventFull> => call('POST', `/events/${id}/seats`, { add }),
  changePlace: (id: Id, place: string): Promise<EventFull> => call('POST', `/events/${id}/place`, { place }), // Studio's "Change room" during the event (Head+)          // "+N seats", the club's Head+: the waitlist moves in
  decline: (id: Id, note?: string): Promise<EventCard> => call('POST', `/events/${id}/decline`, note ? { note } : {}), // a leaders meeting or a club meeting: "Can't make it" (§4.10, §2b: why, required)
  leadersAnswers: (id: Id): Promise<LeadersAnswer[]> => call('GET', `/events/${id}/leaders`), // DMP: the answers per club
  meetingAnswers: (id: Id): Promise<MeetingAnswer[]> => call('GET', `/events/${id}/meeting`), // a club meeting's Head+: everyone expected (§2b)
  register: (id: Id, ref?: string, phone?: string, answers?: { q: string; a: string }[], team?: TeamPick): Promise<EventCard> => call('POST', `/events/${id}/registration`, { ...(ref ? { ref } : {}), ...(phone ? { phone } : {}), ...(answers ? { answers } : {}), ...(team ? { team } : {}) }), // team: a team event's choice (create, join by link) // answers: each with its question's words // ref: a member's code from their link; phone: asked at the sign-up, kept (needsPhone)
  unregister: (id: Id): Promise<EventCard> => call('DELETE', `/events/${id}/registration`),
  setSaved: (id: Id, on: boolean): Promise<void> => call(on ? 'PUT' : 'DELETE', `/events/${id}/saved`),

  orgs: (): Promise<Org[]> => call('GET', '/orgs'),
  // admin (pilot): clubs and their teams; who = @username or a Telegram ID of someone who opened the app once
  adminOrgs: (): Promise<AdminOrg[]> => call('GET', '/admin/orgs'),
  adminOrgEvents: (org: Id): Promise<AdminEvent[]> => call('GET', `/admin/orgs/${org}/events`),
  setRegUntil: (id: Id, until: Ts | 'now' | null): Promise<EventFull> => call('PUT', `/events/${id}/reg-until`, { until }), // registration closes now / then / at the start
  openDoor: (id: Id): Promise<EventFull> => call('POST', `/events/${id}/door-open`), // the President or a Vice opens check-in early (from 4 h before the start)
  // the club's own team (SPEC §2, the rank rule): Vice+ manage people below them, the President hands the club over
  team: (org: Id): Promise<TeamMember[]> => call('GET', `/orgs/${org}/members`),
  /** everyone in a club or school, as anyone sees them (403 when the club hides the list) */
  people: (org: Id): Promise<Member[]> => call('GET', `/orgs/${org}/people`),
  // the club's invite link (§4.5, Vice+): the same token until replaced; a student who opens it is a Member at once
  invite: (org: Id, dept?: Id): Promise<{ token: string }> => call('POST', `/orgs/${org}/invites`, dept ? { dept } : {}), // dept: the newcomer lands in that department
  acceptInvite: (token: string): Promise<Org> => call('POST', `/invites/${token}`),
  teamLink: (org: Id): Promise<{ token: string; expiresAt: Ts }> => call('POST', `/orgs/${org}/team-link`), // the link for the whole team, 7 days: the live one, else a new one
  teamLinkOff: (org: Id): Promise<void> => call('DELETE', `/orgs/${org}/team-link`),
  removeMember: (org: Id, user: Id): Promise<void> => call('DELETE', `/orgs/${org}/members/${user}`), // my own id = leave; a President: conflict/'president'
  transfer: (org: Id, user: Id): Promise<TeamMember[]> => call('POST', `/orgs/${org}/transfer`, { userId: user }),
  // Team 2.0 (§2b): the club's own roles (Vice+) and tags (Head+), probation, removal by request, bans
  teamSetup: (org: Id): Promise<TeamSetup> => call('GET', `/orgs/${org}/team`),
  saveRole: (org: Id, input: { name: string; tr?: Partial<Record<'ru' | 'kk' | 'en', string>>; color: string; rights: Right[] }, id?: Id): Promise<TeamSetup> => (id == null ? call('POST', `/orgs/${org}/roles`, input) : call('PATCH', `/orgs/${org}/roles/${id}`, input)), // conflict/'taken'
  deleteRole: (org: Id, id: Id): Promise<TeamSetup> => call('DELETE', `/orgs/${org}/roles/${id}`),
  assignRole: (org: Id, id: Id, users: Id[]): Promise<{ team: TeamMember[]; setup: TeamSetup; skipped: number }> => call('PUT', `/orgs/${org}/roles/${id}/people`, { users }), // ticked get it, the rest lose it
  saveTag: (org: Id, input: { name: string; color: string; department?: boolean }, id?: Id): Promise<TeamSetup> => (id == null ? call('POST', `/orgs/${org}/tags`, input) : call('PATCH', `/orgs/${org}/tags/${id}`, input)),
  deleteTag: (org: Id, id: Id): Promise<TeamSetup> => call('DELETE', `/orgs/${org}/tags/${id}`),
  updateMember: (org: Id, user: Id, patch: MemberPatch): Promise<TeamMember[]> => call('PATCH', `/orgs/${org}/members/${user}`, patch),
  removeFromClub: (org: Id, user: Id, ban: boolean, note: string): Promise<{ done: boolean }> => call('POST', `/orgs/${org}/members/${user}/remove`, { ban, note }), // a Head's: a request (done: false)
  decideRemoval: (id: Id, approve: boolean): Promise<void> => call('POST', `/removals/${id}`, { approve }),
  unban: (org: Id, user: Id): Promise<void> => call('DELETE', `/orgs/${org}/bans/${user}`),
  adminCreateOrg: (i: { name: string; short: string; emoji: string; official: boolean }): Promise<AdminOrg> => call('POST', '/admin/orgs', i),
  adminSetRole: (org: Id, who: string, role: OrgRole | 'none'): Promise<AdminOrg> => call('PUT', `/admin/orgs/${org}/role`, { who, role }),
  adminHideOrg: (org: Id, hidden: boolean): Promise<AdminOrg> => call('PUT', `/admin/orgs/${org}/hidden`, { hidden }), // hide, never delete
  adminPresLink: (org: Id): Promise<{ token: string; expiresAt: Ts }> => call('POST', `/admin/orgs/${org}/president-link`), // the President's one-time link, shown as a QR
  org: (id: Id): Promise<Org> => call('GET', `/orgs/${id}`),
  subscribe: (id: Id, on: boolean): Promise<Org> => call(on ? 'PUT' : 'DELETE', `/orgs/${id}/subscription`),
  apply: (org: Id, answers?: Record<string, string | string[]>): Promise<Org> => call('POST', `/orgs/${org}/join-requests`, answers ? { answers } : undefined), // join application (§4.5)
  withdraw: (org: Id): Promise<Org> => call('DELETE', `/orgs/${org}/join-requests/mine`),

  schedule: (): Promise<ClassItem[]> => call('GET', '/me/schedule'),
  deleteSchedule: (): Promise<void> => call('DELETE', '/me/schedule'), // my week gone from the server (the Week sheet)

  posts: (scope: 'all' | 'subs' | 'clubs' | { org: Id }): Promise<Post[]> => call('GET', '/posts?scope=' + encodeURIComponent(typeof scope === 'string' ? scope : `org:${scope.org}`)),
  react: (postId: Id, kind: 'fire' | 'heart', on: boolean): Promise<Post> => call(on ? 'PUT' : 'DELETE', `/posts/${postId}/reactions/${kind}`),
  createPost: (org: Id, input: PostInput): Promise<Post> => call('POST', `/orgs/${org}/posts`, input), // Head+ (§4.10); a broadcast tells every club member
  updatePost: (id: Id, patch: PostPatch): Promise<Post> => call('PATCH', `/posts/${id}`, patch), // the club's Head+: text, label, photo ("edited"), the pin
  castings: (): Promise<Post[]> => call('GET', '/castings'), // the Clubs tab's strip: not over yet, soonest first
  cancelCasting: (id: Id): Promise<Post> => call('POST', `/posts/${id}/casting/cancel`), // the club's Head+
  hidePost: (id: Id): Promise<void> => call('DELETE', `/posts/${id}`), // the club's Head+ or the admin
  readPosts: (ids: Id[]): Promise<void> => call('POST', '/posts/read', { ids }), // seen in News: unread marks go
  postVideo: (id: Id): Promise<{ src: string; poster: string | null }> => call('GET', `/posts/${id}/video`), // a channel's video: its CDN file (expires); 404 → the widget

  // a badge held in several variants (a performer who also volunteered): each shows (owner, Nov 2)
  person: (id: Id): Promise<PersonCard> => call<PersonCard>('GET', `/users/${id}`).then((p) => (p?.awards ? { ...p, awards: { ...p.awards, achievements: splitVariants(p.awards.achievements) } } : p)),

  // friends (§4.7): a request the other one answers, or my one invite link (r_<code>) whose landing makes friends in one tap
  friends: (): Promise<Friends> => call('GET', '/friends'),
  findFriend: (username: string): Promise<FoundStudent> => call('GET', '/friends/find?username=' + encodeURIComponent(username)), // not_found: no student with that @username
  askFriend: (user: Id): Promise<{ person: PersonRef; friendship: Friendship }> => call('POST', '/friends/requests', { userId: user }), // 'friends' when they had asked me
  answerFriend: (user: Id, accept: boolean): Promise<Friends> => call('POST', `/friends/requests/${user}/${accept ? 'accept' : 'decline'}`),
  takeBackRequest: (user: Id): Promise<void> => call('DELETE', `/friends/requests/${user}`),
  unfriend: (user: Id): Promise<void> => call('DELETE', `/friends/${user}`),
  linkCard: (code: string): Promise<LinkCard> => call('GET', `/invite/${code}`), // whose invite link it is (adds nobody; guests too)
  addByLink: (code: string): Promise<{ person: PersonRef; friendship: Friendship }> => call('POST', `/invite/${code}`), // friends at once ('requested': they quietly declined me)
  friendJoined: (since: Ts): Promise<{ usedBy: PersonRef | null; at: Ts }> => call('GET', `/friends/joined?since=${since}`), // my invite QR on screen: the newest friend since

  // Studio (own org, SPEC §6): Member+ reads and scans, Head+ creates, edits and sees attendees
  orgEvents: (org: Id): Promise<EventCard[]> => call('GET', `/orgs/${org}/events`),
  /** next week's memo to DMP, signed by me (Head+) */
  memo: (org: Id, later?: boolean): Promise<MemoDraft> => call('GET', `/orgs/${org}/memo${later ? '?later=true' : ''}`),
  /** "Open in Outlook" / "Copy": the others see it */
  memoOpened: (org: Id): Promise<void> => call('POST', `/orgs/${org}/memo/opened`),
  /** "Sent it to DMP?" -> Yes: these events leave the next memos */
  memoSent: (org: Id, ids: Id[]): Promise<void> => call('POST', `/orgs/${org}/memo/sent`, { ids }),
  memoAgain: (org: Id, event: Id): Promise<void> => call('POST', `/orgs/${org}/memo/again/${event}`),
  /** one memo item written from the sheet's small form (no event needed) */
  /** indoor routes' graph (PLAN item 22); the admin saves it from the version he edited (conflict: someone saved since) */
  mapGraph: (): Promise<Graph> => call('GET', '/map/graph'),
  mapRooms: (): Promise<{ updated: string; rooms: Record<string, Record<string, number[]>> }> => call('GET', '/map/rooms'), // "free now" on the map; 404 when off (ROOMS_FILE)
  memoItem: (org: Id, item: { kind: string; fields: object; place: string; startsAt: Ts; endsAt: Ts | null }): Promise<string> => call<{ text: string }>('POST', `/orgs/${org}/memo/item`, item).then((r) => r.text),
  /** my Latin name and positions, fixed once; empty = computed */
  memoSign: (org: Id, sign: MemoSign): Promise<MemoDraft> => call('PUT', `/orgs/${org}/memo/sign`, sign),
  // casting (a club's recruitment round): the team opens and runs it, students apply
  round: (org: Id): Promise<Round | null> => call('GET', `/orgs/${org}/round`),
  openRound: (org: Id, input: RoundInput): Promise<Round> => call('POST', `/orgs/${org}/round`, input),
  updateRound: (id: Id, patch: Partial<RoundInput> & { close?: boolean }): Promise<Round> => call('PATCH', `/rounds/${id}`, patch),
  applyRound: (id: Id, body: { departments: Id[]; answers: Record<string, string | string[]>; source?: string }): Promise<Round> => call('POST', `/rounds/${id}/apply`, body),
  withdrawRound: (id: Id): Promise<Round | null> => call('DELETE', `/rounds/${id}/apply`),
  roundApps: (id: Id): Promise<RoundApp[]> => call('GET', `/rounds/${id}/apps`),
  voteApp: (id: Id, body: { verdict: 'no' | 'maybe' | 'next'; stars?: number | null; note?: string }): Promise<{ stage: AppStage }> => call('POST', `/round-apps/${id}/vote`, body),
  decideApp: (id: Id, body: { stage: AppStage; tagId?: Id | null }): Promise<{ stage: AppStage; takenTag: Id | null }> => call('POST', `/round-apps/${id}/decide`, body),
  /** the results decided so far (the round goes on); final: the undecided get a no and the round ends */
  sendRound: (id: Id, final: boolean): Promise<{ accepted: number; declined: number }> => call('POST', `/rounds/${id}/send`, { final }),
  // interviews: the team's slots and invitations, an invited applicant's time
  roundSlots: (id: Id): Promise<RoundSlot[]> => call('GET', `/rounds/${id}/slots`),
  addSlots: (id: Id, body: { date: string; from: string; to: string; minutes: number; capacity: number; place: string }): Promise<RoundSlot[]> => call('POST', `/rounds/${id}/slots`, body),
  dropSlot: (id: Id): Promise<RoundSlot[]> => call('DELETE', `/round-slots/${id}`),
  inviteRound: (id: Id): Promise<{ invited: number }> => call('POST', `/rounds/${id}/invite`),
  bookSlot: (id: Id, slotId: Id | null): Promise<RoundSlot[]> => call('POST', `/rounds/${id}/book`, { slotId }),
  markShowed: (app: Id, came: boolean | null): Promise<{ showed: boolean | null }> => call('POST', `/round-apps/${app}/came`, { came }),
  createEvent: (org: Id, input: EventInput): Promise<EventFull> => call('POST', `/orgs/${org}/events`, input), // a draft
  updateEvent: (id: Id, input: EventInput): Promise<EventFull> => call('PATCH', `/events/${id}`, input),
  publishEvent: (id: Id): Promise<EventFull & { told?: boolean; tellAfter?: number | null }> => call('POST', `/events/${id}/publish`), // told: the followers heard (a public event); else from when they may
  cancelEvent: (id: Id): Promise<EventFull> => call('POST', `/events/${id}/cancel`),
  deleteEvent: (id: Id): Promise<void> => call('DELETE', `/events/${id}`), // drafts only
  attendees: (id: Id): Promise<Attendee[]> => call('GET', `/events/${id}/attendees`), // the co-host's event team too, without receipts
  /** a co-host club (server logic/cohosts.py): the host's Head+ invites one or ends it; the co-host's Vice+ answers in
   *  Studio (its invites) or leaves */
  cohostInvite: (id: Id, org: Id): Promise<EventFull> => call('PUT', `/events/${id}/cohost`, { orgId: org }),
  cohostEnd: (id: Id): Promise<void> => call('DELETE', `/events/${id}/cohost`),
  cohostAnswer: (id: Id, yes: boolean, mute: boolean = false): Promise<CohostInvite[]> => call('POST', `/events/${id}/cohost/answer`, { yes, mute }), // mute: "don't suggest again" (that host club)
  cohostUnmute: (org: Id, host: Id): Promise<void> => call('DELETE', `/orgs/${org}/mutes/${host}`),
  /** the volunteers ledger (server logic/vol.py): readers the list, a volunteer their own; edits the President's, each with a reason */
  /** appeals to the Student Government (server logic/appeals.py); consent: the section's version, on the first send or AI help */
  appeals: (): Promise<{ items: Appeal[]; solved: Solved[] }> => call('GET', '/appeals'), // solved: the public feed (students: from 3 entries)
  sendAppeal: (a: { text: string; topic: AppealTopic | null; anon: boolean; key: string; consent?: string }): Promise<Appeal> => call('POST', '/appeals', a),
  dropAppeal: (id: Id): Promise<void> => call('DELETE', `/appeals/${id}`),
  appealHelp: (text: string, lang: string, consent?: string): Promise<AppealHelp> => call('POST', '/appeals/help', { text, lang, consent }),
  sgQueue: (): Promise<SgQueue> => call('GET', '/sg/appeals'),
  sgAppeal: (id: Id): Promise<Appeal> => call('GET', `/sg/appeals/${id}`),
  sgAct: (id: Id, change: { status?: AppealStatus; answer?: string }): Promise<Appeal> => call('POST', `/sg/appeals/${id}`, change),
  solvedAdd: (e: { raised: string; changed: string; topic: AppealTopic | null }): Promise<Solved> => call('POST', '/sg/solved', e),
  solvedDrop: (id: Id): Promise<void> => call('DELETE', `/sg/solved/${id}`),
  solvedRestore: (id: Id): Promise<Solved> => call('POST', `/sg/solved/${id}/restore`), // the delete's Undo (a day)
  volLedger: (): Promise<VolLedger> => call('GET', '/vol'),
  volMine: (): Promise<VolPerson> => call('GET', '/vol/mine'),
  volPerson: (id: Id): Promise<VolPerson> => call('GET', `/vol/people/${id}`),
  volLink: (id: Id, user: Id | null): Promise<VolPerson> => call('POST', `/vol/people/${id}/link`, { user }),
  volShiftGone: (id: Id, gone: boolean, reason: string): Promise<VolPerson> => call('PATCH', `/vol/shifts/${id}`, { gone, reason }), // taken out or back; nobody types hours or times
  volDoor: (session: Id): Promise<VolDoor> => call('GET', `/vol/meets/${session}/door`),
  volResolve: (shift: Id, left: Ts | null): Promise<VolDoor> => call('POST', `/vol/shifts/${shift}/resolve`, { left }), // left null: "was here until the end"
  volHand: (session: Id): Promise<VolDoor & { token: string }> => call('POST', `/vol/meets/${session}/hand`), // the one-time link's token, given once
  volUnhand: (session: Id): Promise<VolDoor> => call('DELETE', `/vol/meets/${session}/hand`),
  volTake: (token: string): Promise<import('./types').ScreenSession> => call('POST', '/vol/hand', { token }), // the link opened: that session, mine to run
  volAddMiss: (id: Id, n: 1 | -1, reason: string): Promise<VolPerson> => call('POST', `/vol/people/${id}/misses`, { n, reason }),
  volDropMiss: (id: Id, reason: string): Promise<VolPerson> => call('POST', `/vol/misses/${id}/drop`, { reason }),
  volTeam: (session: Id, team: boolean): Promise<VolLedger> => call('POST', `/vol/meets/${session}`, { team }),
  volAccess: (user: Id, on: boolean): Promise<VolLedger> => call('POST', '/vol/access', { user, on }),
  /** door helpers (server logic/crew.py): a running club's President or Vice gives a student the scanner or the door */
  crewPut: (id: Id, user: Id, kind: CrewKind): Promise<CrewMember[]> => call('PUT', `/events/${id}/crew`, { userId: user, kind }),
  crewDrop: (id: Id, user: Id): Promise<CrewMember[]> => call('DELETE', `/events/${id}/crew/${user}`),
  /** a club's report after its event (server logic/evreports.py): read, its fields, one person's mark (null: off) */
  eventReport: (id: Id, org?: Id): Promise<EventReport> => call('GET', `/events/${id}/report${org ? `?org=${org}` : ''}`), // org: the co-host's own report (the host's without it)
  eventReportSave: (id: Id, patch: ReportPatch, org?: Id): Promise<EventReport> => call('PATCH', `/events/${id}/report${org ? `?org=${org}` : ''}`, patch),
  eventReportMark: (id: Id, user: Id, status: ReportMark | null, org?: Id): Promise<EventReport> => call('PUT', `/events/${id}/report/marks/${user}${org ? `?org=${org}` : ''}`, { status }),
  /** the feature's own consent, mine: given (the version shown) or withdrawn (my marks and author links go) */
  reportConsent: (version: string | null): Promise<{ consent: boolean }> => (version ? call('POST', '/reports/consent', { consent: version }) : call('DELETE', '/reports/consent')),
  cohostInvites: (org: Id): Promise<CohostInvite[]> => call('GET', `/orgs/${org}/cohosts`),
  /** volunteers: I apply (a short "why") or take it back; the organizers list them and say yes or no */
  /** "Create chat": Telegram's add-the-bot-to-a-group link for this event */
  chatStart: (id: Id): Promise<string> => call<{ url: string }>('POST', `/events/${id}/chat`).then((r) => r.url),
  volunteer: (id: Id, note: string): Promise<EventFull> => call('POST', `/events/${id}/volunteer`, { note }),
  volunteerLeave: (id: Id): Promise<EventFull> => call('DELETE', `/events/${id}/volunteer`),
  volunteers: (id: Id): Promise<VolunteerApp[]> => call('GET', `/events/${id}/volunteers`),
  volunteerDecide: (id: Id, user: Id, yes: boolean): Promise<VolunteerApp[]> => call('PUT', `/events/${id}/volunteers/${user}`, { yes }),
  /** team events (server evteams.py): mine (make, join by link, leave; the captain's name, "find us teammates", remove),
   *  an invite link's team, and the organizer's list, Form teams and moves (team null: no team) */
  teamCreate: (id: Id, name: string): Promise<EventFull> => call('POST', `/events/${id}/team`, { name }),
  teamJoin: (id: Id, token: string): Promise<EventFull> => call('POST', `/events/${id}/team/join`, { token }),
  teamLeave: (id: Id): Promise<EventFull> => call('DELETE', `/events/${id}/team`),
  teamEdit: (id: Id, change: { name?: string; open?: boolean }): Promise<EventFull> => call('PATCH', `/events/${id}/team`, change),
  teamNewLink: (id: Id): Promise<EventFull> => call('POST', `/events/${id}/team/link`),
  teamConsent: (version: string | null): Promise<{ consent: boolean }> => (version ? call('POST', '/teams/consent', { consent: version }) : call('DELETE', '/teams/consent')), // teams' own consent: given (its version) or taken back (null)                  // the captain's: a fresh token, the old link stops working
  teamRemove: (id: Id, user: Id): Promise<EventFull> => call('DELETE', `/events/${id}/team/members/${user}`),
  teamInvite: (token: string): Promise<TeamInvite> => call('GET', `/team-invites/${encodeURIComponent(token)}`),
  teams: (id: Id): Promise<TeamsBoard> => call('GET', `/events/${id}/teams`),
  teamsForm: (id: Id): Promise<TeamsBoard> => call('POST', `/events/${id}/teams/form`),
  teamsMove: (id: Id, user: Id, team: Id | null): Promise<TeamsBoard> => call('PUT', `/events/${id}/teams/people/${user}`, { team }),
  /** the host club's member asks its President or a Vice to come as a guest, or takes it back; they list and answer */
  teamAsk: (id: Id): Promise<EventCard> => call('POST', `/events/${id}/team-ask`),
  teamUnask: (id: Id): Promise<EventCard> => call('DELETE', `/events/${id}/team-ask`),
  teamAsks: (id: Id): Promise<TeamAsk[]> => call('GET', `/events/${id}/team-asks`),
  teamDecide: (id: Id, user: Id, yes: boolean): Promise<void> => call('PUT', `/events/${id}/team-asks/${user}`, { yes }),
  /** the bot sends the attendee list as a CSV to my chat; forbidden/'no_dm' when it can't write to me */
  exportAttendees: (id: Id): Promise<void> => call('POST', `/events/${id}/attendees/export`),
  exportMembers: (oid: Id): Promise<void> => call('POST', `/orgs/${oid}/members/export`),
  guardJoin: (t: string): Promise<{ ok: boolean }> => call('POST', '/guard', { t }),
  pickOrgChat: (oid: Id, kind: 'group' | 'channel'): Promise<{ url: string }> => call('POST', `/orgs/${oid}/chats/pick`, { kind }),
  checkin: (id: Id, code: string): Promise<CheckinResult> => call('POST', `/events/${id}/checkin`, { code }),
  // no QR at the door (a dead phone): the door list and a check-in by name, taken back within 10 min (§4.4)
  door: (id: Id): Promise<DoorPerson[]> => call('GET', `/events/${id}/door`),
  // the organizer's updates (Head+, three a day): pinned on the event, the bot pings the people going
  postUpdate: (id: Id, body: string): Promise<EventUpdate[]> => call('POST', `/events/${id}/updates`, { body }),
  rate: (id: Id, score: number, comment?: string): Promise<EventFull> => call('PUT', `/events/${id}/rating`, { score, comment: comment ?? '' }), // one tap after the event (checked-in people)
  deleteUpdate: (id: Id, update: Id): Promise<void> => call('DELETE', `/events/${id}/updates/${update}`),
  checkinPerson: (id: Id, user: Id): Promise<CheckinResult> => call('POST', `/events/${id}/checkin`, { userId: user }),
  undoCheckin: (id: Id, user: Id): Promise<void> => call('DELETE', `/events/${id}/checkin/${user}`),
  uploadPhoto: (file: Blob): Promise<Media> => call('POST', '/photos', file), // Head+; re-encoded by the server, use its id as coverId
  uploadVideo, // Head+; in pieces, then compressed: its id as videoId (wide: wideVideoId)
  video: (id: Id): Promise<Video> => call('GET', `/videos/${id}`), // my upload, while it is compressed
  /** Paid events (§4.3): my receipt for the seat I hold → the ticket at once (Kaspi's PDF or an image; the server reads it). */
  uploadReceipt: (event: Id, file: Blob): Promise<EventCard> => call('POST', `/events/${event}/receipt`, file),
  /** A receipt's image (its sender, the event's Head+, the admin), as an object URL to show. */
  receiptImage: async (id: Id): Promise<string> => {
    // private (§4.3): it needs Telegram's initData, which an <img src> can't send
    const r = await fetch(`/api/receipts/${id}/image`, { headers: { Authorization: `tma ${tg.initData}` } }).catch(() => null);
    if (!r?.ok) throw new ApiErr(r?.status === 404 ? 'not_found' : 'unavailable');
    return URL.createObjectURL(await r.blob());
  },
  /** Head+: the receipt is fine, or rejected (the ticket stops working, the seat goes on, the bot tells the student). */
  reviewReceipt: (id: Id, reject: boolean): Promise<void> => call('POST', `/receipts/${id}/review`, { reject }),
  comments: (kind: 'post' | 'event', id: Id): Promise<CommentThread> => call('GET', `/${kind}s/${id}/comments`), // students (§4.10)
  addComment: (kind: 'post' | 'event', id: Id, body: string, asOrg?: boolean, replyTo?: Id | null): Promise<CommentThread> => call('POST', `/${kind}s/${id}/comments`, { body, asOrg: !!asOrg, ...(replyTo ? { replyTo } : {}) }), // 500 chars, 10 a minute
  setComments: (kind: 'post' | 'event', id: Id, on: boolean): Promise<CommentThread> => call('PATCH', `/${kind}s/${id}/comments`, { on }), // the club's Head+
  deleteComment: (id: Id): Promise<void> => call('DELETE', `/comments/${id}`), // mine, or as the club's Head+
  report: (target: 'comment' | 'post' | 'event' | 'user' | 'photo' | 'ask' | 'fpost', id: Id, reason: ReportReason, note?: string): Promise<void> => call('POST', '/reports', { target, id, reason, note }), // → the moderators' queue
  reports: (): Promise<ReportItem[]> => call('GET', '/admin/reports'), // admin
  // the forum (F1 find people): 404 with the server's flag off, 403 for students while it's tried out
  forumMe: (): Promise<ForumMe> => call('GET', '/forum/me'),
  setForumMe: (patch: Partial<{ skills: Id[]; open: boolean; pings: boolean }>): Promise<ForumMe> => call('PUT', '/forum/me', patch),
  skills: (q: string): Promise<Skill[]> => call('GET', `/forum/skills?q=${encodeURIComponent(q)}`),
  newSkill: (name: string, force?: boolean): Promise<{ skill?: Skill; didYouMean?: Skill[] }> => call('POST', '/forum/skills', { name, force }),
  asks: (skill?: Id | null): Promise<Ask[]> => call('GET', `/forum/asks${skill ? `?skill=${skill}` : ''}`),
  newAsk: (a: AskInput): Promise<Ask> => call('POST', '/forum/asks', a),
  closeAsk: (id: Id, found: boolean | null): Promise<Ask> => call('POST', `/forum/asks/${id}/close`, { found }),
  askPeople: (id: Id): Promise<ForumCard[]> => call('GET', `/forum/asks/${id}/people`),
  findPeople: (q: string, skill?: Id | null): Promise<ForumCard[]> => call('GET', `/forum/people?q=${encodeURIComponent(q)}${skill ? `&skill=${skill}` : ''}`),
  contacts: (): Promise<Contact[]> => call('GET', '/forum/contacts'),
  offer: (to: { ask?: Id; to?: Id }): Promise<{ status: 'pending' }> => call('POST', '/forum/contacts', to),
  answerOffer: (id: Id, yes: boolean): Promise<Contact[]> => call('POST', `/forum/contacts/${id}`, { yes }),
  block: (user: Id, on: boolean = true): Promise<void> => call('POST', '/forum/blocks', { user, on }),
  forumMod: (): Promise<ForumMod> => call('GET', '/forum/mod'), // moderators: held requests, new skills
  releaseAsk: (id: Id): Promise<Ask> => call('POST', `/forum/asks/${id}/release`),
  hideAsk: (id: Id): Promise<void> => call('POST', `/forum/asks/${id}/hide`),
  skillMod: (id: Id, change: { approve?: true; name?: string; into?: Id; delete?: true }): Promise<Skill | null> => call('PATCH', `/forum/skills/${id}`, change),
  refer: (code: string): Promise<void> => call('POST', '/referral', { code }), // opened by someone's invite link
  channelRevealed: (): Promise<{ revealed: number; next: number | null /* when I may post again (the pace); null: now */ }> => call('GET', '/forum-posts/revealed'), // how many anonymous authors were ever revealed (a count)
  channelFeed: (before?: number): Promise<import('./types').ChannelFeedPost[]> => call('GET', `/forum-posts/feed${before ? `?before=${before}` : ''}`), // the Forum tab: the channel's posts and my own, newest first, 50 a page (before: the last id shown)
  newChannelPost: (body: string, anon: boolean, photos: Id[] = []): Promise<import('./types').ChannelPost> => call('POST', '/forum-posts', { body, anon, photos }), // the AI first, live: the bot posts it; photos: uploadChannelPhoto's ids (anonymous with photos: a moderator first)
  uploadChannelPhoto: (file: Blob): Promise<Media & { id: Id }> => call('POST', '/forum-posts/photos', file), // a photo for my next post, re-encoded (no EXIF); unposted ones go in an hour
  appealChannelPost: (id: Id, body: string, photos: Id[] = []): Promise<import('./types').ChannelPost> => call('POST', `/forum-posts/${id}/appeal`, { body, photos }), // refused by the AI: to a moderator (3 a day), the words given back
  channelPostWhy: (id: Id, body: string): Promise<{ explain: import('./types').ForumWhy | null }> => call('POST', `/forum-posts/${id}/why`, { body }), // the AI's reason for my refused or held post, once
  channelReplyWhy: (id: Id): Promise<{ explain: import('./types').ForumWhy | null }> => call('POST', `/forum-replies/${id}/why`), // the same for my held reply
  deleteChannelPost: (id: Id): Promise<void> => call('DELETE', `/forum-posts/${id}`), // mine: the bot takes it out of the channel
  channelMod: (): Promise<import('./types').ChannelMod> => call('GET', '/forum-posts/mod'), // moderators: held, and this week's live
  channelModDecide: (id: Id, ok: boolean): Promise<void> => call('POST', `/forum-posts/${id}/mod`, { ok }), // held: out or removed; live: only removed
  channelModRestore: (id: Id): Promise<void> => call('POST', `/forum-posts/${id}/restore`), // a moderator's take-down undone: published anew
  channelModRepublish: (id: Id): Promise<void> => call('POST', `/forum-posts/${id}/republish`), // a live post sent anew (its message lost in Telegram)
  revealChannelPost: (id: Id): Promise<PersonRef> => call('POST', `/forum-posts/${id}/reveal`), // the owner alone; audited
  channelReplies: (post: Id): Promise<import('./types').ChannelReply[]> => call('GET', `/forum-posts/${post}/replies`), // my replies under my anonymous post
  newChannelReply: (post: Id, body: string, link: string): Promise<import('./types').ChannelReply> => call('POST', `/forum-posts/${post}/replies`, { body, link }), // the AI first; the bot sends it seconds later
  deleteChannelReply: (id: Id): Promise<void> => call('DELETE', `/forum-replies/${id}`), // mine: out of the group
  channelReplyMod: (id: Id, ok: boolean, again: boolean = false): Promise<void> => call('POST', `/forum-replies/${id}/mod`, { ok, again }), // held: out or removed; live: kept or taken down; again: a lost send, re-sent
  channelReplyRestore: (id: Id): Promise<void> => call('POST', `/forum-replies/${id}/restore`), // a take-down undone
  mapFlaw: (f: { ver: string; floor: number; u: number; v: number; px: number; py: number; body: string }): Promise<void> => call('POST', '/map/flaws', f), // a long press on the map
  mapFlaws: (): Promise<{ id: Id; ver: string; floor: number; u: number; v: number; px: number | null; py: number | null; body: string; at: Ts; done: Ts | null }[]> => call('GET', '/map/flaws'), // the admin
  mapFlawsMine: (): Promise<{ id: Id; ver: string; floor: number; u: number; v: number; px: number | null; py: number | null; body: string }[]> => call('GET', '/map/flaws/mine'), // my own open ones, pins on the map
  mapFlawDone: (id: Id, done: boolean): Promise<void> => call('POST', `/map/flaws/${id}/done`, { done }),
  assistant: (q: string, history: { role: 'user' | 'assistant'; text: string }[], context?: { kind: 'event' | 'club'; id: Id }): Promise<AssistReply> => call('POST', '/assistant', { q, history, context }), // the students' assistant; context: the card it was asked from (the server reads its facts)
  assistantVote: (mark: string, vote: 'up' | 'down'): Promise<void> => call('POST', '/assistant/vote', { mark, vote }), // 👍/👎 on an answer's signed topic
  assistantSend: (mark: string, pair: string, q: string, a: string): Promise<void> => call('POST', '/assistant/send', { mark, pair, q, a }), // on 👎, the student's own tap: this one signed question and answer, no name
  eventFill: (org: Id, text: string, have?: Partial<{ title: string; description: string; date: string; start: string; end: string; place: string; price: number }>): Promise<{ title?: string; date?: string; start?: string; end?: string; place?: string; description?: string; price?: number; emoji?: string; color?: string }> => call('POST', `/orgs/${org}/events/fill`, have ? { text, have } : { text }), // a new event from its announcement (AI); emoji and color: its cover when no photo
  qrCheckin: (p: string): Promise<{ title: string; done: boolean; left?: boolean; event?: Id | null; again?: boolean; already?: Ts; flagged?: boolean; team?: boolean /* marked on the event's team list, not as a guest */ }> => call('POST', '/checkin', { p }), // a scan of the big screen's QR (ci_…): done = counted, else waits for my sign-up
  screens: (): Promise<import('./types').ScreenSession[]> => call('GET', '/screens'), // the check-in sessions I run (/show)
  bindScreen: (code: string, session?: Id): Promise<import('./types').ScreenSession> => call('POST', '/screens/bind', { code, session }), // a scan of /show's pairing QR (sh_…); conflict/pick: say which session
  screenAct: (id: Id, act: 'start' | 'finish' | 'unpair' | 'out' | 'in' | 'show'): Promise<import('./types').ScreenSession> => call('POST', `/screens/${id}/${act}`), // out/in: the QR marks leaving or arriving; show: this phone is showing it (the lease, checkin.py)
  screenHand: (id: Id): Promise<import('./types').ScreenSession> => call('POST', `/screens/${id}/helpers`), // the QR that lets someone help run it (hq_…); param is that QR, helpers how many
  screenHandsOff: (id: Id): Promise<import('./types').ScreenSession> => call('DELETE', `/screens/${id}/helpers`), // every helper out
  qrHelper: (p: string, join?: boolean): Promise<import('./types').ScreenHelper> => call('POST', '/screens/helper', { p, join }), // a scan of that QR; join: yes, I'll help
  eventScreen: (event: Id): Promise<import('./types').ScreenSession> => call('POST', `/events/${event}/screen`), // an event's own session, made on first use (organizers)
  clubScreen: (org: Id, title: string, who: 'club' | 'all' | Id): Promise<import('./types').ScreenSession> => call('POST', `/orgs/${org}/screens`, { title, who }), // a club's own session, no event (who runs its sessions; capped); who: the expected list frozen now (a tag's id: its people)
  screenBadge: (id: Id, qr: string): Promise<{ person: string; done: boolean }> => call('POST', `/screens/${id}/badge`, { qr }), // marked by hand: a student's badge QR scanned by who runs it
  screenPeople: (id: Id): Promise<{ came: string[]; other: string[]; absent: string[] }> => call('GET', `/screens/${id}/people`), // the host's three lists: the members who came, who came not on the list, the members who haven't
  crewScreen: (event: Id, title: string): Promise<import('./types').ScreenSession> => call('POST', `/events/${event}/crew-screen`, { title }), // an event's team marked: its club's session, made once (the one there is after)
  crewScreenOf: (event: Id): Promise<import('./types').ScreenSession | null> => call('GET', `/events/${event}/crew-screen`), // ... the one there is, if any
  screenCsv: (id: Id): Promise<{ url: string; name: string }> => call('POST', `/screens/${id}/csv`), // a short-lived link for Telegram's download
  screenGrant: (id: Id, code: string): Promise<{ granted: number; batch: string }> => call('POST', `/screens/${id}/grant`, { code }), // the owner: an award to everyone counted (Admin → Awards); undoBatch(batch)
  restore: (target: TakenDown['target'], id: Id): Promise<void> => call('POST', `/admin/taken-down/${target}/${id}/restore`), // admin: undo one
  resolveReport: (target: ReportItem['target'], id: Id, remove: boolean, abuse?: boolean, rule?: TgcRule): Promise<void> => call('POST', `/admin/reports/${target}/${id}`, { remove, abuse, rule }), // admin: take it down or leave it (a Telegram comment: the terms clause it broke, or the reports were abuse)
  tgComment: (): Promise<TgComment | null> => call('POST', '/me/tg-comment'), // my own deleted Telegram comment, to me alone
  myClubApplication: (): Promise<ClubApplication | null> => call<{ application: ClubApplication | null }>('GET', '/club-applications/mine').then((r) => r.application), // starting a club (§4.6): my latest application
  applyClub: (input: ClubApplicationInput): Promise<ClubApplication> => call('POST', '/club-applications', input),
  decideClubApplication: (id: Id, approve: boolean, reason?: string): Promise<ClubApplication> => call('POST', `/admin/club-applications/${id}`, { approve, reason: reason ?? '' }),
  officialPath: (org: Id): Promise<OfficialPath | null> => call<{ path: OfficialPath | null }>('GET', `/orgs/${org}/official-path`).then((r) => r.path), // the club's team: the Ascent's checklist (null: official already)
  askOfficial: (org: Id): Promise<OfficialPath | null> => call<{ path: OfficialPath | null }>('POST', `/orgs/${org}/official-path`).then((r) => r.path), // its President or a Vice, at the top: asks DMP for the ✓
  decideOfficial: (id: Id, approve: boolean, reason?: string): Promise<OfficialRequest> => call('POST', `/admin/official-requests/${id}`, { approve, reason: reason ?? '' }), // admin
  feature: (postId: Id, days: number): Promise<Post> => call('POST', '/admin/feature', { postId, days }), // admin: on top of List for everyone; 0 ends it
  /** Admin → Awards: give a person a manual award (the bot sends them its card); undo: ungrant(its id) */
  giveGrant: (userId: Id, code: GrantItem['code'], orgId?: Id): Promise<GrantItem> => call('POST', '/admin/grants', { userId, code, orgId }), // orgId: Club founder's club
  /** the scanner: a person's card QR is one grant; `run` names this opening of the camera for undoBatch('s_' + run) */
  grantScan: (qr: string, code: GrantItem['code'], run?: string): Promise<GrantItem> => call('POST', '/admin/grants/scan', { qr, code, run }),
  /** undo a scanner run ('s_…'), a link's people ('l_' + token), a check-in session's (screenGrant's batch) */
  undoBatch: (batch: string): Promise<{ undone: number }> => call('POST', '/admin/grants/undo', { batch }),
  /** Admin → Awards' rows: how many hold each award (a badge once a person); who holds one, newest first */
  awardCounts: (): Promise<Record<string, number>> => call('GET', '/admin/awards'),
  awardPeople: (award: string): Promise<GrantItem[]> => call('GET', `/admin/awards/${award}/people`),
  /** one person's manual awards (the chips) */
  awardsOf: (userId: Id): Promise<import('./types').BadgeHolder> => call('GET', `/admin/grants/of/${userId}`),
  /** my award links of the last 30 days, live first, with who used each; revoke stops one now */
  grantLinks: (): Promise<import('./types').GrantLink[]> => call('GET', '/admin/grant-links'),
  revokeLink: (token: string): Promise<void> => call('DELETE', `/admin/grant-links/${token}`),
  /** undo one of my grants, at any time */
  ungrant: (id: Id): Promise<void> => call('DELETE', `/admin/grants/${id}`),
  /** a manual award back off a person, at any time (a mistake): every grant of it */
  takeBackGrant: (userId: Id, code: GrantItem['code']): Promise<import('./types').BadgeHolder> => call('POST', '/admin/grants/take-back', { userId, code }),
  useGrantLink: (token: string): Promise<{ code: string }> => call('POST', `/grant-links/${token}`),
  /** Admin → Awards → Show QR: open one for an award, its current code (closing it: revokeLink); a student's scan of it */
  openBadgeQr: (code: GrantItem['code']): Promise<import('./types').BadgeQr> => call('POST', '/admin/badge-qr', { code }),
  badgeQr: (token: string): Promise<import('./types').BadgeQr> => call('GET', `/admin/badge-qr/${token}`),
  claimBadgeQr: (p: string): Promise<{ code: string }> => call('POST', '/badge-qr', { p }),
  /** find a student with their manual awards; the owner's check-in sessions */
  badgeSessions: (): Promise<import('./types').BadgeSession[]> => call('GET', '/admin/badges/sessions'),
  staff: (): Promise<Staff> => call('GET', '/admin/staff'), // admin: the app's team and the banned
  staffSearch: (q: string): Promise<StaffRow[]> => call('GET', '/admin/people?q=' + encodeURIComponent(q)),
  search: (q: string): Promise<{ events: EventCard[]; clubs: OrgRef[] }> => call('GET', '/search?q=' + encodeURIComponent(q)), // the one search: by any name, what I may see (the admin: all)
  staffMutes: (): Promise<import('./types').StaffMute[]> => call('GET', '/admin/notifications'), // staff: my work-item notifications
  setStaffMute: (kind: string, on: boolean): Promise<import('./types').StaffMute[]> => call('PUT', `/admin/notifications/${kind}`, { on }), // admin → People: by name, @username, student ID or id
  inbox: (): Promise<import('./types').Inbox> => call('GET', '/admin/inbox'), // staff: everything waiting, and what was done lately
  undoDone: (id: Id): Promise<void> => call('POST', `/admin/done/${id}/undo`), // a Done row taken back (each undo keeps its own rules)
  adminDeleteEvent: (id: Id): Promise<void> => call('DELETE', `/admin/events/${id}`), // admin: hidden now, gone in a day (Undo till then)
  setStaff: (userId: Id, role: PlatformRole): Promise<Staff> => call('POST', '/admin/staff', { userId, role }), // admin role: the owner only
  ban: (userId: Id, on: boolean, reason?: string): Promise<Staff> => call('POST', '/admin/ban', { userId, on, reason: reason ?? null }), // a reason to ban (he sees it)
  audit: (): Promise<AuditRow[]> => call('GET', '/admin/audit'), // the owner: the last 200 actions done with power
  adminStats: (): Promise<AdminStats> => call('GET', '/admin/stats'),
  adminDay: (day: number): Promise<AdminDay> => call('GET', `/admin/stats/${day}`),
  adminAi: (): Promise<AdminAi> => call('GET', '/admin/ai'),
  aiRetry: (): Promise<void> => call('POST', '/admin/ai/retry'),
  chats: (): Promise<Chats> => call('GET', '/chats'), // the chats directory (§4.11)
  /** any chat suggested from the app: @name, a t.me link or an invite link */
  suggestChat: (link: string): Promise<{ status: 'sent' | 'waiting' | 'exists' | 'org' | 'limit' | 'later' | 'slow' | 'notchat' | 'bad'; title: string }> => call('POST', '/chats/suggest', { link }),
  chatOpened: (id: Id): Promise<void> => call('POST', `/chats/${id}/opened`), // the tick
  addChat: (input: { title: string; url: string; kind: Chat['kind']; school: string | null; course: number | null }): Promise<Chat> => call('POST', '/admin/chats', input), // moderators, admin
  setChatOrg: (id: Id, org: Id | null): Promise<Chat> => call('PUT', `/admin/chats/${id}/org`, { orgId: org }), // the admin: whose a catalog chat is (PLAN 86)
  setChatSection: (id: Id, section: ChatSection): Promise<Chat> => call('PUT', `/admin/chats/${id}/section`, { section }), // staff: what a chat is for (the AI's mark goes)
  orgChats: (org: Id): Promise<StudioChat[]> => call('GET', `/orgs/${org}/chats`), // Vice+ (and the admin): the org's chats in Studio
  addOrgChat: (org: Id, link: string): Promise<StudioChat[]> => call('POST', `/orgs/${org}/chats`, { link }), // @name, t.me link or invite link; bad_input notchat, conflict taken / limit, unavailable
  mainOrgChat: (org: Id, chat: Id): Promise<StudioChat[]> => call('PUT', `/orgs/${org}/chats/${chat}/main`), // a public channel only
  dropOrgChat: (org: Id, chat: Id): Promise<StudioChat[]> => call('DELETE', `/orgs/${org}/chats/${chat}`),
  waitingChats: (org: Id): Promise<WaitingChat[]> => call('GET', `/orgs/${org}/chats/waiting`), // chats I made our bot an admin in, mine to link here
  linkWaitingChat: (org: Id, wait: Id): Promise<StudioChat[]> => call('POST', `/orgs/${org}/chats/waiting/${wait}`), // conflict rights: the bot or I no longer its admin; taken / not_found
  rosterSeen: (): Promise<void> => call('POST', '/roster/seen'), // PLAN 95: the join toasts shown
  rosterClaim: (row: Id): Promise<void> => call('POST', `/roster/${row}/claim`), // "Yes, it's me" on a row under another name
  rosterRequests: (org?: Id): Promise<RosterRequest[]> => call('GET', org ? `/roster/requests?org=${org}` : '/roster/requests'), // the claims I confirm (President; DMP for a club without one)
  rosterDecide: (row: Id, ok: boolean): Promise<void> => call('POST', `/roster/requests/${row}`, { ok }), // the main channel's posts in the club's news
  mirrorOrgChat: (org: Id, chat: Id, on: boolean): Promise<StudioChat[]> => call('PUT', `/orgs/${org}/chats/${chat}/mirror`, { on }),
  swearOrgChat: (org: Id, chat: Id, on: boolean): Promise<StudioChat[]> => call('PUT', `/orgs/${org}/chats/${chat}/swear`, { on }), // President or Vice; conflict rights: the bot can't delete and restrict there
  swearReport: (org: Id): Promise<SwearRow[]> => call('GET', `/orgs/${org}/chats/swear`), // President, Vice, Heads
  chatRoles: (org: Id, chat: Id): Promise<ChatRoles> => call('GET', `/orgs/${org}/chats/${chat}/roles`), // the group's admins against the club's roles, asked of Telegram now
  deleteChat: (id: Id): Promise<void> => call('DELETE', `/admin/chats/${id}`), // a suggestion declined too
  approveChat: (id: Id): Promise<Chat> => call('POST', `/admin/chats/${id}/approve`), // a suggested chat into the catalog
  registry: (back: number = 0): Promise<RegistryOrg[]> => call('GET', `/registry/orgs?back=${back}`), // DMP Head+ and the admin (§4.13); a month `back` months ago (0–12)
  registryRoster: (org: Id): Promise<RosterMember[]> => call('GET', `/registry/orgs/${org}/members`),
  /** DMP Head+ (and the admin) give a club the ✓ or take it back; its President hears it from the bot */
  setOfficial: (org: Id, on: boolean): Promise<OrgRef> => call('POST', `/registry/orgs/${org}/official`, { on }),
  registryMemos: (): Promise<SentMemo[]> => call('GET', '/registry/memos'), // the memos clubs marked sent in the last 7 days
  registrySearch: (q: string): Promise<RegistryHit[]> => call('GET', `/registry/search?q=${encodeURIComponent(q)}`), // a club member by name or student ID
  registryExport: (): Promise<void> => call('POST', '/registry/export'), // every roster as a CSV into my chat with the bot
  markUnlocked: (code: string, level: number): Promise<{ unlocked: Me['unlocked'] }> => call('POST', '/me/unlocked', { code, level }), // the unlock moment was shown
  anthemHeard: (): Promise<{ unlocked: Me['unlocked'] }> => call('POST', '/me/anthem'), // the anthem heard start to finish without skipping: its award (once)
  calendarFeed: (): Promise<{ page: string; feed: string }> => call('POST', '/me/calendar'), // my events in the phone's calendar (a kept secret address)
  resetCalendar: (): Promise<void> => call('DELETE', '/me/calendar'), // the old address stops; the next calendarFeed() makes a new one
  eventInvites: (id: Id): Promise<FriendInvite[]> => call('GET', `/events/${id}/invites`), // "Bring a friend": my friends and where they stand
  inviteFriend: (id: Id, userId: Id): Promise<FriendInvite[]> => call('POST', `/events/${id}/invites`, { userId }), // the bot brings them our card; once per friend and event
  addAlbumPhoto: (id: Id, file: Blob): Promise<EventFull> => call('POST', `/events/${id}/photos`, file), // the guests' album (canAddPhotos); re-encoded like a cover
  removeAlbumPhoto: (id: Id, photo: Id): Promise<EventFull> => call('DELETE', `/events/${id}/photos/${photo}`), // mine, or any as the club's Head+
  // Vice+: applications and whether the club takes them
  joinRequests: (org: Id): Promise<JoinRequest[]> => call('GET', `/orgs/${org}/join-requests`),
  decideJoin: (id: Id, accept: boolean): Promise<void> => call('POST', `/join-requests/${id}/${accept ? 'accept' : 'reject'}`),
  setRecruiting: (org: Id, on: boolean): Promise<Org> => call('PATCH', `/orgs/${org}`, { recruiting: on }),
  /** the club's profile (Vice+): name, letters, emoji, cover, about, links */
  updateOrg: (org: Id, patch: OrgPatch): Promise<Org> => call('PATCH', `/orgs/${org}`, patch),
  deleteOrg: async (org: Id): Promise<void> => { await call('DELETE', `/orgs/${org}`); }, // the President's own empty club (made by mistake)
  shortLinks: (org: Id): Promise<ShortLink[]> => call('GET', `/orgs/${org}/links`), // Vice+
  addShortLink: (org: Id, link: { slug: string; kind: ShortLink['kind']; eventId?: Id }): Promise<ShortLink[]> => call('POST', `/orgs/${org}/links`, link), // conflict 'taken' / 'limit'
  dropShortLink: (slug: string): Promise<void> => call('DELETE', `/links/${slug}`), // the club's Vice+, or the admin revoking it

};
