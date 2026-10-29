// The real server (SPEC §6). Every call carries Telegram's signed initData; errors come back as
// { error, message } and become ApiErr.
import type { Api } from './index';
import type { ApiError, ClubApplication, Id, Video } from './types';
import { ApiErr } from './errors';
import { tg } from '../tg';
import { i18n } from '../i18n/index.svelte';

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let r: Response;
  const raw = body instanceof Blob; // a file goes as the body itself (POST /api/photos)
  try {
    r = await fetch('/api' + path, {
      method,
      headers: { Authorization: `tma ${tg.initData}`, ...(body === undefined ? {} : { 'Content-Type': raw ? body.type || 'application/octet-stream' : 'application/json' }) },
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiErr('unavailable', 'network');
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  // banned mid-session: the app hears it from any call, not only at launch
  if (r.status === 403 && (data as ApiError | null)?.message === 'banned') dispatchEvent(new CustomEvent('kb:banned', { detail: data }));
  if (!r.ok) throw new ApiErr((data as ApiError | null)?.error ?? 'unavailable', (data as ApiError | null)?.message || undefined, (data as Record<string, unknown> | null) ?? {});
  return localize(data) as T;
}

// what the server has in the viewer's language (PLAN 9): a school's name, description and short name (kbtu.edu.kz), a
// club's description and an event's title and description (ai.py). The text as typed stays in `orig`, so a second pass
// (another language, a copy from the cache) starts from it and the editors save it, never a translation.
const SHOWN = ['name', 'title', 'description', 'body'] as const; // body: a channel's post (PLAN 86)
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

export const server: Api = {
  me: () => call('GET', '/me'),
  msStart: () => call('POST', '/ms/start'),
  manualLogin: (i, consentVersion) => call('POST', '/kbtu/manual', { ...i, consentVersion }),
  updateMe: (patch) => call('PATCH', '/me', patch),
  uploadMyPhoto: (file) => call('POST', '/me/photo', file),
  deleteMyPhoto: () => call('DELETE', '/me/photo'),
  deleteMe: (photos = false) => call('POST', '/me/delete', { photos }),
  deleteInfo: () => call('GET', '/me/delete'),
  consent: (version) => call('POST', '/me/consent', { version }),
  keepMe: () => call('POST', '/me/keep'),
  dmOn: (event?: Id) => call('POST', '/me/dm', { event }),

  events: (q = {}) => call('GET', '/events' + query({ from: q.from, to: q.to, org: q.org })),
  pastEvents: () => call('GET', '/events/past'),
  event: (id) => call('GET', `/events/${id}`),
  addSeats: (id, add) => call('POST', `/events/${id}/seats`, { add }),
  changePlace: (id, place) => call('POST', `/events/${id}/place`, { place }),
  decline: (id, note) => call('POST', `/events/${id}/decline`, note ? { note } : {}),
  leadersAnswers: (id) => call('GET', `/events/${id}/leaders`),
  meetingAnswers: (id) => call('GET', `/events/${id}/meeting`),
  register: (id, ref, phone, answers) => call('POST', `/events/${id}/registration`, { ...(ref ? { ref } : {}), ...(phone ? { phone } : {}), ...(answers ? { answers } : {}) }),
  unregister: (id) => call('DELETE', `/events/${id}/registration`),
  setSaved: (id, on) => call(on ? 'PUT' : 'DELETE', `/events/${id}/saved`),
  tickets: () => call('GET', '/me/tickets'),

  orgs: () => call('GET', '/orgs'),
  adminOrgs: () => call('GET', '/admin/orgs'),
  adminOrgEvents: (org) => call('GET', `/admin/orgs/${org}/events`),
  team: (org) => call('GET', `/orgs/${org}/members`),
  people: (org) => call('GET', `/orgs/${org}/people`),
  invite: (org, dept) => call('POST', `/orgs/${org}/invites`, dept ? { dept } : {}),
  acceptInvite: (token) => call('POST', `/invites/${token}`),
  changeRole: (org, user, role) => call('PATCH', `/orgs/${org}/members/${user}`, { role }),
  removeMember: (org, user) => call('DELETE', `/orgs/${org}/members/${user}`),
  transfer: (org, user) => call('POST', `/orgs/${org}/transfer`, { userId: user }),
  teamSetup: (org) => call('GET', `/orgs/${org}/team`),
  saveRole: (org, input, id) => (id == null ? call('POST', `/orgs/${org}/roles`, input) : call('PATCH', `/orgs/${org}/roles/${id}`, input)),
  deleteRole: (org, id) => call('DELETE', `/orgs/${org}/roles/${id}`),
  saveTag: (org, input, id) => (id == null ? call('POST', `/orgs/${org}/tags`, input) : call('PATCH', `/orgs/${org}/tags/${id}`, input)),
  deleteTag: (org, id) => call('DELETE', `/orgs/${org}/tags/${id}`),
  updateMember: (org, user, patch) => call('PATCH', `/orgs/${org}/members/${user}`, patch),
  removeFromClub: (org, user, ban, note) => call('POST', `/orgs/${org}/members/${user}/remove`, { ban, note }),
  decideRemoval: (id, approve) => call('POST', `/removals/${id}`, { approve }),
  unban: (org, user) => call('DELETE', `/orgs/${org}/bans/${user}`),
  adminCreateOrg: (i) => call('POST', '/admin/orgs', i),
  adminSetRole: (org, who, role) => call('PUT', `/admin/orgs/${org}/role`, { who, role }),
  adminHideOrg: (org, hidden) => call('PUT', `/admin/orgs/${org}/hidden`, { hidden }),
  adminPresLink: (org) => call('POST', `/admin/orgs/${org}/president-link`),
  org: (id) => call('GET', `/orgs/${id}`),
  subscribe: (id, on) => call(on ? 'PUT' : 'DELETE', `/orgs/${id}/subscription`),
  apply: (org) => call('POST', `/orgs/${org}/join-requests`),
  withdraw: (org) => call('DELETE', `/orgs/${org}/join-requests/mine`),

  schedule: () => call('GET', '/me/schedule'),

  posts: (scope) => call('GET', '/posts?scope=' + encodeURIComponent(typeof scope === 'string' ? scope : `org:${scope.org}`)),
  react: (postId, kind, on) => call(on ? 'PUT' : 'DELETE', `/posts/${postId}/reactions/${kind}`),
  createPost: (org, input) => call('POST', `/orgs/${org}/posts`, input),
  updatePost: (id, patch) => call('PATCH', `/posts/${id}`, patch),
  hidePost: (id) => call('DELETE', `/posts/${id}`),
  readPosts: (ids) => call('POST', '/posts/read', { ids }),

  person: (id) => call('GET', `/users/${id}`),

  friends: () => call('GET', '/friends'),
  findFriend: (username) => call('GET', '/friends/find?username=' + encodeURIComponent(username)),
  askFriend: (user) => call('POST', '/friends/requests', { userId: user }),
  answerFriend: (user, accept) => call('POST', `/friends/requests/${user}/${accept ? 'accept' : 'decline'}`),
  takeBackRequest: (user) => call('DELETE', `/friends/requests/${user}`),
  unfriend: (user) => call('DELETE', `/friends/${user}`),
  friendLink: () => call('POST', '/friends/link'),
  friendLinkUsed: (token) => call('GET', `/friends/link/${token}`),
  useFriendLink: (token) => call('POST', `/friends/link/${token}`),

  orgEvents: (org) => call('GET', `/orgs/${org}/events`),
  memo: (org, later) => call('GET', `/orgs/${org}/memo${later ? '?later=true' : ''}`),
  memoOpened: (org) => call('POST', `/orgs/${org}/memo/opened`),
  memoSent: (org, ids) => call('POST', `/orgs/${org}/memo/sent`, { ids }),
  memoAgain: (org, event) => call('POST', `/orgs/${org}/memo/again/${event}`),
  mapGraph: () => call('GET', '/map/graph'),
  saveMapGraph: (g) => call('PUT', '/map/graph', g),
  memoItem: (org, item) => call<{ text: string }>('POST', `/orgs/${org}/memo/item`, item).then((r) => r.text),
  memoSign: (org, sign) => call('PUT', `/orgs/${org}/memo/sign`, sign),
  round: (org) => call('GET', `/orgs/${org}/round`),
  openRound: (org, input) => call('POST', `/orgs/${org}/round`, input),
  updateRound: (id, patch) => call('PATCH', `/rounds/${id}`, patch),
  applyRound: (id, body) => call('POST', `/rounds/${id}/apply`, body),
  withdrawRound: (id) => call('DELETE', `/rounds/${id}/apply`),
  roundApps: (id) => call('GET', `/rounds/${id}/apps`),
  voteApp: (id, body) => call('POST', `/round-apps/${id}/vote`, body),
  decideApp: (id, body) => call('POST', `/round-apps/${id}/decide`, body),
  sendRound: (id) => call('POST', `/rounds/${id}/send`),
  roundSlots: (id) => call('GET', `/rounds/${id}/slots`),
  addSlots: (id, body) => call('POST', `/rounds/${id}/slots`, body),
  dropSlot: (id) => call('DELETE', `/round-slots/${id}`),
  inviteRound: (id) => call('POST', `/rounds/${id}/invite`),
  bookSlot: (id, slotId) => call('POST', `/rounds/${id}/book`, { slotId }),
  markShowed: (app, came) => call('POST', `/round-apps/${app}/came`, { came }),
  createEvent: (org, input) => call('POST', `/orgs/${org}/events`, input),
  updateEvent: (id, input) => call('PATCH', `/events/${id}`, input),
  publishEvent: (id) => call('POST', `/events/${id}/publish`),
  cancelEvent: (id) => call('POST', `/events/${id}/cancel`),
  deleteEvent: (id) => call('DELETE', `/events/${id}`),
  attendees: (id) => call('GET', `/events/${id}/attendees`),
  chatStart: (id) => call<{ url: string }>('POST', `/events/${id}/chat`).then((r) => r.url),
  volunteer: (id, note) => call('POST', `/events/${id}/volunteer`, { note }),
  volunteerLeave: (id) => call('DELETE', `/events/${id}/volunteer`),
  volunteers: (id) => call('GET', `/events/${id}/volunteers`),
  volunteerDecide: (id, user, yes) => call('PUT', `/events/${id}/volunteers/${user}`, { yes }),
  exportAttendees: (id) => call('POST', `/events/${id}/attendees/export`),
  checkin: (id, code) => call('POST', `/events/${id}/checkin`, { code }),
  door: (id) => call('GET', `/events/${id}/door`),
  postUpdate: (id, body) => call('POST', `/events/${id}/updates`, { body }),
  rate: (id, score, comment) => call('PUT', `/events/${id}/rating`, { score, comment: comment ?? '' }),
  deleteUpdate: (id, update) => call('DELETE', `/events/${id}/updates/${update}`),
  checkinPerson: (id, user) => call('POST', `/events/${id}/checkin`, { userId: user }),
  undoCheckin: (id, user) => call('DELETE', `/events/${id}/checkin/${user}`),
  doorGuests: (id) => call('GET', `/events/${id}/door/guests`),
  addDoorGuest: (id, name) => call('POST', `/events/${id}/door/guests`, { name }),
  undoDoorGuest: (id, guest) => call('DELETE', `/events/${id}/door/guests/${guest}`),
  uploadPhoto: (file) => call('POST', '/photos', file),
  uploadVideo,
  video: (id) => call('GET', `/videos/${id}`),
  uploadReceipt: (event, file) => call('POST', `/events/${event}/receipt`, file),
  receiptImage: async (id) => {
    // private (§4.3): it needs Telegram's initData, which an <img src> can't send
    const r = await fetch(`/api/receipts/${id}/image`, { headers: { Authorization: `tma ${tg.initData}` } }).catch(() => null);
    if (!r?.ok) throw new ApiErr(r?.status === 404 ? 'not_found' : 'unavailable');
    return URL.createObjectURL(await r.blob());
  },
  reviewReceipt: (id, reject) => call('POST', `/receipts/${id}/review`, { reject }),
  comments: (kind, id) => call('GET', `/${kind}s/${id}/comments`),
  addComment: (kind, id, body, asOrg, replyTo) => call('POST', `/${kind}s/${id}/comments`, { body, asOrg: !!asOrg, ...(replyTo ? { replyTo } : {}) }),
  setComments: (kind, id, on) => call('PATCH', `/${kind}s/${id}/comments`, { on }),
  deleteComment: (id) => call('DELETE', `/comments/${id}`),
  report: (target, id, reason, note) => call('POST', '/reports', { target, id, reason, note }),
  reports: () => call('GET', '/admin/reports'),
  takenDown: () => call('GET', '/admin/taken-down'),
  forumMe: () => call('GET', '/forum/me'),
  setForumMe: (patch) => call('PUT', '/forum/me', patch),
  skills: (q) => call('GET', `/forum/skills?q=${encodeURIComponent(q)}`),
  newSkill: (name, force) => call('POST', '/forum/skills', { name, force }),
  asks: (skill) => call('GET', `/forum/asks${skill ? `?skill=${skill}` : ''}`),
  newAsk: (a) => call('POST', '/forum/asks', a),
  closeAsk: (id, found) => call('POST', `/forum/asks/${id}/close`, { found }),
  askPeople: (id) => call('GET', `/forum/asks/${id}/people`),
  findPeople: (q, skill) => call('GET', `/forum/people?q=${encodeURIComponent(q)}${skill ? `&skill=${skill}` : ''}`),
  contacts: () => call('GET', '/forum/contacts'),
  offer: (to) => call('POST', '/forum/contacts', to),
  answerOffer: (id, yes) => call('POST', `/forum/contacts/${id}`, { yes }),
  block: (user, on = true) => call('POST', '/forum/blocks', { user, on }),
  forumMod: () => call('GET', '/forum/mod'),
  releaseAsk: (id) => call('POST', `/forum/asks/${id}/release`),
  hideAsk: (id) => call('POST', `/forum/asks/${id}/hide`),
  skillMod: (id, change) => call('PATCH', `/forum/skills/${id}`, change),
  refer: (code) => call('POST', '/referral', { code }),
  threads: (topic, before, bid) => call('GET', '/threads' + query({ topic: topic ?? undefined, before, bid })),
  thread: (id) => call('GET', `/threads/${id}`),
  newThread: (input) => call('POST', '/threads', input),
  deleteThread: (id) => call('DELETE', `/threads/${id}`),
  replyThread: (id, body, anon) => call('POST', `/threads/${id}/replies`, { body, anon }),
  deleteReply: (id) => call('DELETE', `/threads/replies/${id}`),
  joinThread: (id, on) => call('PUT', `/threads/${id}/join`, { on }),
  threadJoiners: (id) => call('GET', `/threads/${id}/joiners`),
  threadMod: () => call('GET', '/threads/mod'),
  threadModDecide: (kind, id, ok) => call('POST', `/threads/mod/${kind}/${id}`, { ok }),
  revealAnon: (kind, id) => call('POST', `/threads/reveal/${kind}/${id}`),
  mapFlaw: (f) => call('POST', '/map/flaws', f),
  mapFlaws: () => call('GET', '/map/flaws'),
  mapFlawDone: (id, done) => call('POST', `/map/flaws/${id}/done`, { done }),
  assistant: (q, history) => call('POST', '/assistant', { q, history }),
  qrCheckin: (p) => call('POST', '/checkin', { p }),
  screens: () => call('GET', '/screens'),
  bindScreen: (code, session) => call('POST', '/screens/bind', { code, session }),
  screenAct: (id, act) => call('POST', `/screens/${id}/${act}`),
  eventScreen: (event) => call('POST', `/events/${event}/screen`),
  screenCsv: (id) => call('POST', `/screens/${id}/csv`),
  restore: (target, id) => call('POST', `/admin/taken-down/${target}/${id}/restore`),
  resolveReport: (target, id, remove) => call('POST', `/admin/reports/${target}/${id}`, { remove }),
  myClubApplication: () => call<{ application: ClubApplication | null }>('GET', '/club-applications/mine').then((r) => r.application),
  applyClub: (input) => call('POST', '/club-applications', input),
  clubApplications: () => call('GET', '/admin/club-applications'),
  decideClubApplication: (id, approve, reason) => call('POST', `/admin/club-applications/${id}`, { approve, reason: reason ?? '' }),
  feature: (postId, days) => call('POST', '/admin/feature', { postId, days }),
  grant: (userId, code) => call('POST', '/admin/grants', { userId, code }),
  grantScan: (qr, code) => call('POST', '/admin/grants/scan', { qr, code }),
  ungrant: (id) => call('DELETE', `/admin/grants/${id}`),
  takeBackGrant: (userId, code) => call('POST', '/admin/grants/take-back', { userId, code }),
  useGrantLink: (token) => call('POST', `/grant-links/${token}`),
  myGrants: () => call('GET', '/admin/grants'),
  staff: () => call('GET', '/admin/staff'),
  staffFind: (username) => call('GET', '/admin/staff/find?username=' + encodeURIComponent(username)),
  setStaff: (userId, role) => call('POST', '/admin/staff', { userId, role }),
  ban: (userId, on, reason) => call('POST', '/admin/ban', { userId, on, reason: reason ?? null }),
  audit: () => call('GET', '/admin/audit'),
  adminStats: () => call('GET', '/admin/stats'),
  adminDay: (day) => call('GET', `/admin/stats/${day}`),
  adminAi: () => call('GET', '/admin/ai'),
  aiRetry: () => call('POST', '/admin/ai/retry'),
  chats: () => call('GET', '/chats'),
  suggestChat: (link) => call('POST', '/chats/suggest', { link }),
  chatOpened: (id) => call('POST', `/chats/${id}/opened`),
  addChat: (input) => call('POST', '/admin/chats', input),
  setChatOrg: (id, org) => call('PUT', `/admin/chats/${id}/org`, { orgId: org }),
  orgChats: (org) => call('GET', `/orgs/${org}/chats`),
  addOrgChat: (org, link) => call('POST', `/orgs/${org}/chats`, { link }),
  mainOrgChat: (org, chat) => call('PUT', `/orgs/${org}/chats/${chat}/main`),
  dropOrgChat: (org, chat) => call('DELETE', `/orgs/${org}/chats/${chat}`),
  rosterSeen: () => call('POST', '/roster/seen'),
  rosterClaim: (row) => call('POST', `/roster/${row}/claim`),
  rosterRequests: () => call('GET', '/roster/requests'),
  rosterDecide: (row, ok) => call('POST', `/roster/requests/${row}`, { ok }),
  mirrorOrgChat: (org, chat, on) => call('PUT', `/orgs/${org}/chats/${chat}/mirror`, { on }),
  deleteChat: (id) => call('DELETE', `/admin/chats/${id}`),
  approveChat: (id) => call('POST', `/admin/chats/${id}/approve`),
  registry: (back = 0) => call('GET', `/registry/orgs?back=${back}`),
  registryRoster: (org) => call('GET', `/registry/orgs/${org}/members`),
  setOfficial: (org, on) => call('POST', `/registry/orgs/${org}/official`, { on }),
  registryMemos: () => call('GET', '/registry/memos'),
  registrySearch: (q) => call('GET', `/registry/search?q=${encodeURIComponent(q)}`),
  registryExport: () => call('POST', '/registry/export'),
  markUnlocked: (code, level) => call('POST', '/me/unlocked', { code, level }),
  calendarFeed: () => call('POST', '/me/calendar'),
  eventInvites: (id) => call('GET', `/events/${id}/invites`),
  inviteFriend: (id, userId) => call('POST', `/events/${id}/invites`, { userId }),
  addAlbumPhoto: (id, file) => call('POST', `/events/${id}/photos`, file),
  removeAlbumPhoto: (id, photo) => call('DELETE', `/events/${id}/photos/${photo}`),
  joinRequests: (org) => call('GET', `/orgs/${org}/join-requests`),
  decideJoin: (id, accept) => call('POST', `/join-requests/${id}/${accept ? 'accept' : 'reject'}`),
  setRecruiting: (org, on) => call('PATCH', `/orgs/${org}`, { recruiting: on }),
  updateOrg: (org, patch) => call('PATCH', `/orgs/${org}`, patch),
  shortLinks: (org) => call('GET', `/orgs/${org}/links`),
  addShortLink: (org, link) => call('POST', `/orgs/${org}/links`, link),
  dropShortLink: (slug) => call('DELETE', `/links/${slug}`),

};
