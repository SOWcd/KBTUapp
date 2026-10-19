// The one door to data: screens import `api` from here (SPEC §8). Until Oct 11 an in-browser mock stood behind it too
// (a second copy of the server's rules, drifting); screens are now checked on the real server with made-up people
// (server/tools/qa.py).
import type {
  AdminOrg, AdminEvent, OrgRole, TeamMember, TeamSetup, ClubLevel, MemberPatch, Strike, Friends, Friendship, FoundStudent, FriendLinkUse, PersonRef, Media, Video, Attendee, DoorPerson, EventUpdate, PostInput, CheckinResult, ClassItem, JoinRequest, EventCard, EventFull, EventInput, Id, Me, Org, PersonCard, Post, Settings, Ts, FriendInvite, CommentThread, ReportReason, ReportItem, RegistryOrg, SentMemo, RosterMember, RegistryHit, Chat, Chats, ClubApplication, ClubApplicationInput, LeadersAnswer, MeetingAnswer, OrgPatch, PostPatch, OrgRef, TakenDown, Right, MemoDraft, MemoSign, GrantItem, AdminStats, Round, RoundInput, RoundApp, AppStage, RoundSlot, VolunteerApp } from './types';
import { server } from './client';
import type { Graph } from '../route';

export * from './types';
export { ApiErr } from './errors';

export interface Api {
  me(): Promise<Me>;
  msStart(): Promise<{ url: string }>; // the KBTU Microsoft sign-in link, opened outside Telegram
  manualLogin(i: { firstName: string; lastName: string; studentId: string; course: number }, consentVersion: string): Promise<Me>; // only while it isn't
  updateMe(patch: Partial<Settings> & { bio?: string; showcase?: string[]; nick?: string | null; avatarTg?: boolean; skin?: Id | 'sower' | null }): Promise<Me>;
  uploadMyPhoto(file: Blob): Promise<Me>;                        // my own photo: "Photo from Telegram" goes off
  deleteMyPhoto(): Promise<Me>;                                  // gone from the server too; Telegram's is back
  /** §4.8, with the KBTU login and password again; a wrong or another student's one: bad_input/'credentials';
   *  a President: conflict/'president'. */
  deleteMe(): Promise<Me>;                                       // in 7 days (Me.deleteAt)
  keepMe(): Promise<Me>;

  events(q?: { from?: Ts; to?: Ts; org?: Id }): Promise<EventCard[]>;
  pastEvents(): Promise<EventCard[]>;
  event(id: Id): Promise<EventFull>;
  register(id: Id, invitedBy?: Id): Promise<EventCard>;
  addSeats(id: Id, add: number): Promise<EventFull>;
  changePlace(id: Id, place: string): Promise<EventFull>;   // Studio's "Change room" during the event (Head+)          // "+N seats", the club's Head+: the waitlist moves in
  decline(id: Id, note?: string): Promise<EventCard>;      // a leaders meeting or a club meeting: "Can't make it" (§4.10, §2b: why, required)
  leadersAnswers(id: Id): Promise<LeadersAnswer[]>;          // DMP: the answers per club
  meetingAnswers(id: Id): Promise<MeetingAnswer[]>;          // a club meeting's Head+: everyone expected (§2b)
  unregister(id: Id): Promise<EventCard>;
  setSaved(id: Id, on: boolean): Promise<void>;
  tickets(): Promise<EventCard[]>;
  /** the psychologist's nearest free hour (unix seconds), null when unknown */
  psych(): Promise<{ next: number | null }>;

  orgs(): Promise<Org[]>;
  // admin (pilot): clubs and their teams; who = @username or a Telegram ID of someone who opened the app once
  adminOrgs(): Promise<AdminOrg[]>;
  adminOrgEvents(org: Id): Promise<AdminEvent[]>;
  adminCreateOrg(i: { name: string; short: string; emoji: string; official: boolean }): Promise<AdminOrg>;
  adminSetRole(org: Id, who: string, role: OrgRole | 'none'): Promise<AdminOrg>;
  adminHideOrg(org: Id, hidden: boolean): Promise<AdminOrg>;          // hide, never delete (owner, Oct 16)
  adminPresLink(org: Id): Promise<{ token: string; expiresAt: Ts }>;  // the President's one-time link, shown as a QR
  org(id: Id): Promise<Org>;
  subscribe(id: Id, on: boolean): Promise<Org>;
  apply(org: Id): Promise<Org>;                                  // join application (§4.5)
  withdraw(org: Id): Promise<Org>;

  schedule(): Promise<ClassItem[]>;

  posts(scope: 'all' | 'subs' | 'clubs' | { org: Id }): Promise<Post[]>;
  react(postId: Id, kind: 'fire' | 'heart', on: boolean): Promise<Post>;
  createPost(org: Id, input: PostInput): Promise<Post>;          // Head+ (§4.10); a broadcast tells every club member
  updatePost(id: Id, patch: PostPatch): Promise<Post>;          // the club's Head+: text, label, photo ("edited"), the pin
  hidePost(id: Id): Promise<void>;                               // the club's Head+ or the admin
  readPosts(ids: Id[]): Promise<void>;                           // seen in News: unread marks go

  person(id: Id): Promise<PersonCard>;

  // friends (§4.7): a request the other one answers, or my one-time link that makes friends at once
  friends(): Promise<Friends>;
  findFriend(username: string): Promise<FoundStudent>;           // not_found: no student with that @username
  askFriend(user: Id): Promise<{ person: PersonRef; friendship: Friendship }>; // 'friends' when they had asked me
  answerFriend(user: Id, accept: boolean): Promise<Friends>;
  takeBackRequest(user: Id): Promise<void>;
  unfriend(user: Id): Promise<void>;
  friendLink(): Promise<{ token: string; expiresAt: Ts }>;       // the same until somebody uses it
  friendLinkUsed(token: string): Promise<{ usedBy: PersonRef | null }>;
  useFriendLink(token: string): Promise<FriendLinkUse>;

  // Studio (own org, SPEC §6): Member+ reads and scans, Head+ creates, edits and sees attendees
  orgEvents(org: Id): Promise<EventCard[]>;
  // casting (a club's recruitment round): the team opens and runs it, students apply
  round(org: Id): Promise<Round | null>;
  openRound(org: Id, input: RoundInput): Promise<Round>;
  updateRound(id: Id, patch: Partial<RoundInput> & { close?: boolean }): Promise<Round>;
  applyRound(id: Id, body: { departments: Id[]; answers: Record<string, string | string[]>; source?: string }): Promise<Round>;
  withdrawRound(id: Id): Promise<Round | null>;
  roundApps(id: Id): Promise<RoundApp[]>;
  voteApp(id: Id, body: { verdict: 'no' | 'maybe' | 'next'; stars?: number | null; note?: string }): Promise<{ stage: AppStage }>;
  decideApp(id: Id, body: { stage: AppStage; tagId?: Id | null }): Promise<{ stage: AppStage; takenTag: Id | null }>;
  sendRound(id: Id): Promise<{ accepted: number; declined: number }>;
  // interviews: the team's slots and invitations, an invited applicant's time
  roundSlots(id: Id): Promise<RoundSlot[]>;
  addSlots(id: Id, body: { date: string; from: string; to: string; minutes: number; capacity: number; place: string }): Promise<RoundSlot[]>;
  dropSlot(id: Id): Promise<RoundSlot[]>;
  inviteRound(id: Id): Promise<{ invited: number }>;
  bookSlot(id: Id, slotId: Id | null): Promise<RoundSlot[]>;
  markShowed(app: Id, came: boolean | null): Promise<{ showed: boolean | null }>;
  /** next week's memo to DMP, signed by me (Head+) */
  memo(org: Id, later?: boolean): Promise<MemoDraft>;
  /** "Open in Outlook" / "Copy": the others see it */
  memoOpened(org: Id): Promise<void>;
  /** "Sent it to DMP?" -> Yes: these events leave the next memos */
  memoSent(org: Id, ids: Id[]): Promise<void>;
  memoAgain(org: Id, event: Id): Promise<void>;
  /** my Latin name and positions, fixed once; empty = computed */
  memoSign(org: Id, sign: MemoSign): Promise<MemoDraft>;
  /** one memo item written from the sheet's small form (no event needed) */
  /** indoor routes' graph (PLAN item 22); the admin saves it from the version he edited (conflict: someone saved since) */
  mapGraph(): Promise<Graph>;
  saveMapGraph(g: Graph): Promise<Graph>;
  memoItem(org: Id, item: { kind: string; fields: object; place: string; startsAt: Ts; endsAt: Ts | null }): Promise<string>;
  createEvent(org: Id, input: EventInput): Promise<EventFull>;   // a draft
  updateEvent(id: Id, input: EventInput): Promise<EventFull>;
  publishEvent(id: Id): Promise<EventFull>;
  cancelEvent(id: Id): Promise<EventFull>;
  deleteEvent(id: Id): Promise<void>;                            // drafts only
  attendees(id: Id): Promise<Attendee[]>;
  /** volunteers: I apply (a short "why") or take it back; the organizers list them and say yes or no */
  /** "Create chat": Telegram's add-the-bot-to-a-group link for this event */
  chatStart(id: Id): Promise<string>;
  volunteer(id: Id, note: string): Promise<EventFull>;
  volunteerLeave(id: Id): Promise<EventFull>;
  volunteers(id: Id): Promise<VolunteerApp[]>;
  volunteerDecide(id: Id, user: Id, yes: boolean): Promise<VolunteerApp[]>;
  /** Paid events (§4.3): my receipt for the seat I hold → the ticket at once (Kaspi's PDF or an image; the server reads it). */
  uploadReceipt(event: Id, file: Blob): Promise<EventCard>;
  /** A receipt's image (its sender, the event's Head+, the admin), as an object URL to show. */
  receiptImage(id: Id): Promise<string>;
  /** Head+: the receipt is fine, or rejected (the ticket stops working, the seat goes on, the bot tells the student). */
  reviewReceipt(id: Id, reject: boolean): Promise<void>;
  /** the bot sends the attendee list as a CSV to my chat; forbidden/'no_dm' when it can't write to me */
  exportAttendees(id: Id): Promise<void>;
  checkin(id: Id, code: string): Promise<CheckinResult>;
  // the organizer's updates (Head+, three a day): pinned on the event, the bot pings the people going
  postUpdate(id: Id, body: string): Promise<EventUpdate[]>;
  rate(id: Id, score: number, comment?: string): Promise<EventFull>; // one tap after the event (checked-in people)
  deleteUpdate(id: Id, update: Id): Promise<void>;
  // no QR at the door (a dead phone): the door list and a check-in by name, taken back within 10 min (§4.4)
  door(id: Id): Promise<DoorPerson[]>;
  checkinPerson(id: Id, user: Id): Promise<CheckinResult>;
  undoCheckin(id: Id, user: Id): Promise<void>;
  comments(kind: 'post' | 'event', id: Id): Promise<CommentThread>;                   // students (§4.10)
  addComment(kind: 'post' | 'event', id: Id, body: string, asOrg?: boolean, replyTo?: Id | null): Promise<CommentThread>; // 500 chars, 10 a minute
  setComments(kind: 'post' | 'event', id: Id, on: boolean): Promise<CommentThread>;  // the club's Head+
  deleteComment(id: Id): Promise<void>;                                              // mine, or as the club's Head+
  report(target: 'comment' | 'post' | 'event' | 'user' | 'photo', id: Id, reason: ReportReason): Promise<void>; // → the admin's queue
  reports(): Promise<ReportItem[]>;                                                  // admin
  takenDown(): Promise<TakenDown[]>;                                                 // admin: the last 30 days' take-downs
  restore(target: TakenDown['target'], id: Id): Promise<void>;                       // admin: undo one
  resolveReport(target: ReportItem['target'], id: Id, remove: boolean): Promise<void>; // admin: take it down or leave it
  myClubApplication(): Promise<ClubApplication | null>;  // starting a club (§4.6): my latest application
  applyClub(input: ClubApplicationInput): Promise<ClubApplication>;
  clubApplications(): Promise<ClubApplication[]>;         // moderators, admin: pending first
  decideClubApplication(id: Id, approve: boolean, reason?: string): Promise<ClubApplication>;
  feature(postId: Id, days: number): Promise<Post>;      // moderators, admin: on top of List for everyone; 0 ends it
  grant(userId: Id, code: 'bugs' | 'creator_laugh' | 'creator_found'): Promise<PersonCard>; // the admin's manual achievements
  /** the owner's batch scanner: a badge QR is one grant; undo within a minute; what I gave */
  grantScan(qr: string, code: GrantItem['code']): Promise<GrantItem>;
  ungrant(id: Id): Promise<void>;
  /** a manual award back off a profile, at any time (a mistake): every grant of it */
  takeBackGrant(userId: Id, code: 'bugs' | 'creator_laugh' | 'creator_found'): Promise<PersonCard>;
  useGrantLink(token: string): Promise<{ code: string }>;
  myGrants(): Promise<GrantItem[]>;
  adminStats(): Promise<AdminStats>;
  chats(): Promise<Chats>;                                // the chats directory (§4.11)
  chatOpened(id: Id): Promise<void>;                      // the tick
  addChat(input: { title: string; url: string; kind: Chat['kind']; school: string | null; course: number | null }): Promise<Chat>; // moderators, admin
  deleteChat(id: Id): Promise<void>;
  registry(back?: number): Promise<RegistryOrg[]>;       // DMP Head+ and the admin (§4.13); a month `back` months ago (0–12)
  registryRoster(org: Id): Promise<RosterMember[]>;
  /** DMP Head+ (and the admin) give a club the ✓ or take it back; its President hears it from the bot */
  setOfficial(org: Id, on: boolean): Promise<OrgRef>;
  registryMemos(): Promise<SentMemo[]>;                   // the memos clubs marked sent in the last 7 days
  registrySearch(q: string): Promise<RegistryHit[]>;      // a club member by name or student ID
  registryExport(): Promise<void>;                        // every roster as a CSV into my chat with the bot
  markUnlocked(code: string, level: number): Promise<{ unlocked: Me['unlocked'] }>; // the unlock moment was shown
  calendarFeed(): Promise<{ page: string; feed: string }>;     // my events in the phone's calendar (a kept secret address)
  eventInvites(id: Id): Promise<FriendInvite[]>;               // "Bring a friend": my friends and where they stand
  inviteFriend(id: Id, userId: Id): Promise<FriendInvite[]>;    // the bot brings them our card; once per friend and event
  addAlbumPhoto(id: Id, file: Blob): Promise<EventFull>;        // the guests' album (canAddPhotos); re-encoded like a cover
  removeAlbumPhoto(id: Id, photo: Id): Promise<EventFull>;      // mine, or any as the club's Head+
  uploadPhoto(file: Blob): Promise<Media>;                       // Head+; re-encoded by the server, use its id as coverId
  uploadVideo(file: Blob, progress: (done: number) => void): Promise<Video>; // Head+; in pieces, then compressed: use its id as videoId
  video(id: Id): Promise<Video>;                                 // my upload, while it is compressed
  // Vice+: applications and whether the club takes them
  joinRequests(org: Id): Promise<JoinRequest[]>;
  // the club's own team (SPEC §2, the rank rule): Vice+ manage people below them, the President hands the club over
  team(org: Id): Promise<TeamMember[]>;
  // the club's invite link (§4.5, Vice+): the same token until replaced; a student who opens it is a Member at once
  invite(org: Id): Promise<{ token: string }>;
  acceptInvite(token: string): Promise<Org>;
  changeRole(org: Id, user: Id, role: OrgRole): Promise<TeamMember[]>;
  removeMember(org: Id, user: Id): Promise<void>;          // my own id = leave; a President: conflict/'president'
  transfer(org: Id, user: Id): Promise<TeamMember[]>;
  // Team 2.0 (§2b): the club's own roles (Vice+) and tags (Head+), probation strikes, removal by request, bans
  teamSetup(org: Id): Promise<TeamSetup>;
  saveRole(org: Id, input: { name: string; color: string; rights: Right[] }, id?: Id): Promise<TeamSetup>;  // conflict/'taken'
  deleteRole(org: Id, id: Id): Promise<TeamSetup>;
  saveTag(org: Id, input: { name: string; color: string }, id?: Id): Promise<TeamSetup>;
  deleteTag(org: Id, id: Id): Promise<TeamSetup>;
  updateMember(org: Id, user: Id, patch: MemberPatch): Promise<TeamMember[]>;
  strikes(org: Id, user: Id): Promise<Strike[]>;         // mine, or anyone's as the club's Head+
  addStrike(org: Id, user: Id, reason: Strike['reason'], note: string, eventId?: Id): Promise<TeamMember[]>; // conflict/'probation': not on it; eventId: a missed meeting, once
  clearStrike(id: Id): Promise<void>;
  removeFromClub(org: Id, user: Id, ban: boolean, note: string): Promise<{ done: boolean }>; // a Head's: a request (done: false)
  decideRemoval(id: Id, approve: boolean): Promise<void>;
  unban(org: Id, user: Id): Promise<void>;
  decideJoin(id: Id, accept: boolean): Promise<void>;
  setRecruiting(org: Id, on: boolean): Promise<Org>;
  /** the club's profile (Vice+): name, letters, emoji, cover, about, links */
  updateOrg(org: Id, patch: OrgPatch): Promise<Org>;

}

export const api: Api = server;
