// The one door to data: screens import `api` from here (SPEC §8). Until Oct 11 an in-browser mock stood behind it too
// (a second copy of the server's rules, drifting); screens are now checked on the real server with made-up people
// (server/tools/qa.py).
import type {
  AdminOrg, AdminEvent, OrgRole, TeamMember, Member, TeamSetup, ClubLevel, MemberPatch, Friends, Friendship, FoundStudent, FriendLinkUse, LinkCard, PersonRef, Media, Video, Attendee, DoorPerson, DoorGuest, EventUpdate, PostInput, CheckinResult, ClassItem, JoinRequest, CohostInvite, CrewKind, CrewMember, EventCard, EventFull, EventInput, Id, Me, Org, PersonCard, Post, Settings, Ts, FriendInvite, CommentThread, ReportReason, ReportItem, RegistryOrg, SentMemo, RosterMember, RegistryHit, Chat, ChatSection, Chats, ClubApplication, ClubApplicationInput, OfficialPath, OfficialRequest, LeadersAnswer, MeetingAnswer, OrgPatch, PostPatch, OrgRef, TakenDown, Staff, StaffRow, AuditRow, PlatformRole, Right, MemoDraft, MemoSign, GrantItem, AdminStats, AdminDay, AdminAi, Round, RoundInput, RoundApp, AppStage, RoundSlot, VolunteerApp, TeamAsk, ShortLink, OrgChat, StudioChat, RosterRequest, Skill, ForumMe, ForumCard, Ask, AskInput, Contact, ForumMod, AssistReply, Fixable, TgComment, TgcClosed, TgcRule } from './types';
import { server } from './client';
import type { Graph } from '../route';

export * from './types';
export { ApiErr } from './errors';
export { localize, original, staffEvents, translated } from './client';

export interface Api {
  me(): Promise<Me>;
  msStart(): Promise<{ url: string }>; // the KBTU Microsoft sign-in link, opened outside Telegram
  manualLogin(i: { firstName: string; lastName: string; studentId: string; course: number }, consentVersion: string): Promise<Me>; // only while it isn't
  updateMe(patch: Partial<Settings> & { bio?: string; showcase?: string[]; nick?: string | null; avatarTg?: boolean; skin?: Id | 'sower' | null; frame?: string | null; phone?: string | null; school?: string | null; course?: number; city?: string | null; cityHidden?: boolean }
    & { [k in Exclude<Fixable, 'course' | 'school'>]?: string }): Promise<Me>;  // phone, city: null deletes it; a Fixable: once each (the server says `fixed` after)
  uploadMyPhoto(file: Blob): Promise<Me>;                        // my own photo: "Photo from Telegram" goes off
  deleteMyPhoto(): Promise<Me>;                                  // gone from the server too; Telegram's is back
  /** §4.8, with the KBTU login and password again; a wrong or another student's one: bad_input/'credentials';
   *  a President: conflict/'president'. */
  deleteMe(photos?: boolean): Promise<Me>;                       // in 7 days (Me.deleteAt); photos: my album photos go too
  deleteInfo(): Promise<{ photos: number; paid: boolean }>;      // what the delete sheet says first
  consent(version: string): Promise<Me>;                         // agree to a new policy version
  keepMe(): Promise<Me>;
  dmOn(event?: Id): Promise<Me>;

  events(q?: { from?: Ts; to?: Ts; org?: Id }): Promise<EventCard[]>;
  pastEvents(org?: Id, mine?: boolean): Promise<EventCard[]>; // org: a club's latest few; mine: the ones I was signed up for or came to
  event(id: Id): Promise<EventFull>;
  register(id: Id, ref?: string, phone?: string, answers?: { q: string; a: string }[]): Promise<EventCard>; // answers: each with its question's words // ref: a member's code from their link; phone: asked at the sign-up, kept (needsPhone)
  addSeats(id: Id, add: number): Promise<EventFull>;
  changePlace(id: Id, place: string): Promise<EventFull>;   // Studio's "Change room" during the event (Head+)          // "+N seats", the club's Head+: the waitlist moves in
  decline(id: Id, note?: string): Promise<EventCard>;      // a leaders meeting or a club meeting: "Can't make it" (§4.10, §2b: why, required)
  leadersAnswers(id: Id): Promise<LeadersAnswer[]>;          // DMP: the answers per club
  meetingAnswers(id: Id): Promise<MeetingAnswer[]>;          // a club meeting's Head+: everyone expected (§2b)
  unregister(id: Id): Promise<EventCard>;
  setSaved(id: Id, on: boolean): Promise<void>;

  orgs(): Promise<Org[]>;
  // admin (pilot): clubs and their teams; who = @username or a Telegram ID of someone who opened the app once
  adminOrgs(): Promise<AdminOrg[]>;
  adminOrgEvents(org: Id): Promise<AdminEvent[]>;
  setRegUntil(id: Id, until: Ts | 'now' | null): Promise<EventFull>; // registration closes now / then / at the start
  openDoor(id: Id): Promise<EventFull>; // the President or a Vice opens check-in early (from 4 h before the start)
  adminCreateOrg(i: { name: string; short: string; emoji: string; official: boolean }): Promise<AdminOrg>;
  adminSetRole(org: Id, who: string, role: OrgRole | 'none'): Promise<AdminOrg>;
  adminHideOrg(org: Id, hidden: boolean): Promise<AdminOrg>;          // hide, never delete
  adminPresLink(org: Id): Promise<{ token: string; expiresAt: Ts }>;  // the President's one-time link, shown as a QR
  org(id: Id): Promise<Org>;
  subscribe(id: Id, on: boolean): Promise<Org>;
  apply(org: Id, answers?: Record<string, string | string[]>): Promise<Org>;                                  // join application (§4.5)
  withdraw(org: Id): Promise<Org>;

  schedule(): Promise<ClassItem[]>;
  deleteSchedule(): Promise<void>;                               // my week gone from the server (the Week sheet)

  posts(scope: 'all' | 'subs' | 'clubs' | { org: Id }): Promise<Post[]>;
  react(postId: Id, kind: 'fire' | 'heart', on: boolean): Promise<Post>;
  createPost(org: Id, input: PostInput): Promise<Post>;          // Head+ (§4.10); a broadcast tells every club member
  updatePost(id: Id, patch: PostPatch): Promise<Post>;          // the club's Head+: text, label, photo ("edited"), the pin
  hidePost(id: Id): Promise<void>;                               // the club's Head+ or the admin
  readPosts(ids: Id[]): Promise<void>;                           // seen in News: unread marks go
  postVideo(id: Id): Promise<{ src: string; poster: string | null }>; // a channel's video: its CDN file (expires); 404 → the widget

  person(id: Id): Promise<PersonCard>;

  // friends (§4.7): a request the other one answers, or my one invite link (r_<code>) whose landing makes friends in one tap
  friends(): Promise<Friends>;
  findFriend(username: string): Promise<FoundStudent>;           // not_found: no student with that @username
  askFriend(user: Id): Promise<{ person: PersonRef; friendship: Friendship }>; // 'friends' when they had asked me
  answerFriend(user: Id, accept: boolean): Promise<Friends>;
  takeBackRequest(user: Id): Promise<void>;
  unfriend(user: Id): Promise<void>;
  linkCard(code: string): Promise<LinkCard>;                     // whose invite link it is (adds nobody; guests too)
  addByLink(code: string): Promise<{ person: PersonRef; friendship: Friendship }>; // friends at once ('requested': they quietly declined me)
  friendJoined(since: Ts): Promise<{ usedBy: PersonRef | null; at: Ts }>; // my invite QR on screen: the newest friend since
  useFriendLink(token: string): Promise<FriendLinkUse>;          // ponytail: the old fr_ links, remove after 2026-11-10

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
  /** the results decided so far (the round goes on); final: the undecided get a no and the round ends */
  sendRound(id: Id, final: boolean): Promise<{ accepted: number; declined: number }>;
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
  memoItem(org: Id, item: { kind: string; fields: object; place: string; startsAt: Ts; endsAt: Ts | null }): Promise<string>;
  createEvent(org: Id, input: EventInput): Promise<EventFull>;   // a draft
  updateEvent(id: Id, input: EventInput): Promise<EventFull>;
  publishEvent(id: Id): Promise<EventFull & { told?: boolean; tellAfter?: number | null }>;  // told: the followers heard (a public event); else from when they may
  cancelEvent(id: Id): Promise<EventFull>;
  deleteEvent(id: Id): Promise<void>;                            // drafts only
  attendees(id: Id): Promise<Attendee[]>;                         // the co-host's event team too, without receipts
  /** a co-host club (server logic/cohosts.py): the host's Head+ invites one or ends it; the co-host's Vice+ answers in
   *  Studio (its invites) or leaves */
  cohostInvite(id: Id, org: Id): Promise<EventFull>;
  cohostEnd(id: Id): Promise<void>;
  cohostAnswer(id: Id, yes: boolean, mute?: boolean): Promise<CohostInvite[]>; // mute: "don't suggest again" (that host club)
  cohostUnmute(org: Id, host: Id): Promise<void>;
  /** door helpers (server logic/crew.py): a running club's President or Vice gives a student the scanner or the door */
  crewPut(id: Id, user: Id, kind: CrewKind): Promise<CrewMember[]>;
  crewDrop(id: Id, user: Id): Promise<CrewMember[]>;
  cohostInvites(org: Id): Promise<CohostInvite[]>;
  /** volunteers: I apply (a short "why") or take it back; the organizers list them and say yes or no */
  /** "Create chat": Telegram's add-the-bot-to-a-group link for this event */
  chatStart(id: Id): Promise<string>;
  volunteer(id: Id, note: string): Promise<EventFull>;
  volunteerLeave(id: Id): Promise<EventFull>;
  volunteers(id: Id): Promise<VolunteerApp[]>;
  volunteerDecide(id: Id, user: Id, yes: boolean): Promise<VolunteerApp[]>;
  /** the host club's member asks its President or a Vice to come as a guest, or takes it back; they list and answer */
  teamAsk(id: Id): Promise<EventCard>;
  teamUnask(id: Id): Promise<EventCard>;
  teamAsks(id: Id): Promise<TeamAsk[]>;
  teamDecide(id: Id, user: Id, yes: boolean): Promise<void>;
  /** Paid events (§4.3): my receipt for the seat I hold → the ticket at once (Kaspi's PDF or an image; the server reads it). */
  uploadReceipt(event: Id, file: Blob): Promise<EventCard>;
  /** A receipt's image (its sender, the event's Head+, the admin), as an object URL to show. */
  receiptImage(id: Id): Promise<string>;
  /** Head+: the receipt is fine, or rejected (the ticket stops working, the seat goes on, the bot tells the student). */
  reviewReceipt(id: Id, reject: boolean): Promise<void>;
  /** the bot sends the attendee list as a CSV to my chat; forbidden/'no_dm' when it can't write to me */
  exportAttendees(id: Id): Promise<void>;
  exportMembers(orgId: Id): Promise<void>;
  guardJoin(token: string): Promise<{ ok: boolean }>;
  pickOrgChat(orgId: Id, kind: 'group' | 'channel'): Promise<{ url: string }>;
  checkin(id: Id, code: string): Promise<CheckinResult>;
  // the organizer's updates (Head+, three a day): pinned on the event, the bot pings the people going
  postUpdate(id: Id, body: string): Promise<EventUpdate[]>;
  rate(id: Id, score: number, comment?: string): Promise<EventFull>; // one tap after the event (checked-in people)
  deleteUpdate(id: Id, update: Id): Promise<void>;
  // no QR at the door (a dead phone): the door list and a check-in by name, taken back within 10 min (§4.4)
  door(id: Id): Promise<DoorPerson[]>;
  checkinPerson(id: Id, user: Id): Promise<CheckinResult>;
  undoCheckin(id: Id, user: Id): Promise<void>;
  doorGuests(id: Id): Promise<DoorGuest[]>;
  addDoorGuest(id: Id, name: string): Promise<DoorGuest>;
  undoDoorGuest(id: Id, guest: Id): Promise<void>;
  comments(kind: 'post' | 'event', id: Id): Promise<CommentThread>;                   // students (§4.10)
  addComment(kind: 'post' | 'event', id: Id, body: string, asOrg?: boolean, replyTo?: Id | null): Promise<CommentThread>; // 500 chars, 10 a minute
  setComments(kind: 'post' | 'event', id: Id, on: boolean): Promise<CommentThread>;  // the club's Head+
  deleteComment(id: Id): Promise<void>;                                              // mine, or as the club's Head+
  report(target: 'comment' | 'post' | 'event' | 'user' | 'photo' | 'ask' | 'fpost', id: Id, reason: ReportReason, note?: string): Promise<void>; // → the moderators' queue
  reports(): Promise<ReportItem[]>;                                                  // admin
  // the forum (F1 find people): 404 with the server's flag off, 403 for students while it's tried out
  forumMe(): Promise<ForumMe>;
  setForumMe(patch: Partial<{ skills: Id[]; open: boolean; pings: boolean }>): Promise<ForumMe>;
  skills(q: string): Promise<Skill[]>;
  newSkill(name: string, force?: boolean): Promise<{ skill?: Skill; didYouMean?: Skill[] }>;
  asks(skill?: Id | null): Promise<Ask[]>;
  newAsk(a: AskInput): Promise<Ask>;
  closeAsk(id: Id, found: boolean | null): Promise<Ask>;
  askPeople(id: Id): Promise<ForumCard[]>;
  findPeople(q: string, skill?: Id | null): Promise<ForumCard[]>;
  contacts(): Promise<Contact[]>;
  offer(to: { ask?: Id; to?: Id }): Promise<{ status: 'pending' }>;
  answerOffer(id: Id, yes: boolean): Promise<Contact[]>;
  block(user: Id, on?: boolean): Promise<void>;
  forumMod(): Promise<ForumMod>;                                                     // moderators: held requests, new skills
  releaseAsk(id: Id): Promise<Ask>;
  hideAsk(id: Id): Promise<void>;
  skillMod(id: Id, change: { approve?: true; name?: string; into?: Id; delete?: true }): Promise<Skill | null>;
  refer(code: string): Promise<void>;                                                 // opened by someone's invite link
  channelFeed(before?: number): Promise<import('./types').ChannelFeedPost[]>;            // the Forum tab: the channel's posts and my own, newest first, 50 a page (before: the last id shown)
  newChannelPost(body: string, anon: boolean): Promise<import('./types').ChannelPost>;   // one a day; the AI first, live: the bot posts it
  appealChannelPost(id: Id, body: string): Promise<import('./types').ChannelPost>;    // refused by the AI: to a moderator (3 a day), the words given back
  channelPostWhy(id: Id, body: string): Promise<{ explain: import('./types').ForumWhy | null }>; // the AI's reason for my refused or held post, once
  channelReplyWhy(id: Id): Promise<{ explain: import('./types').ForumWhy | null }>;      // the same for my held reply
  deleteChannelPost(id: Id): Promise<void>;                                             // mine: the bot takes it out of the channel
  channelRevealed(): Promise<{ revealed: number }>;                                      // how many anonymous authors were ever revealed (a count)
  channelMod(): Promise<import('./types').ChannelMod>;                                  // moderators: held, and this week's live
  channelModDecide(id: Id, ok: boolean): Promise<void>;                                 // held: out or removed; live: only removed
  channelModRepublish(id: Id): Promise<void>;                                           // a live post sent anew (its message lost in Telegram)
  channelModRestore(id: Id): Promise<void>;                                            // a moderator's take-down undone: published anew
  revealChannelPost(id: Id): Promise<PersonRef>;                                        // the owner alone; audited
  channelReplies(post: Id): Promise<import('./types').ChannelReply[]>;                   // my replies under my anonymous post
  newChannelReply(post: Id, body: string, link: string): Promise<import('./types').ChannelReply>; // the AI first; the bot sends it seconds later
  deleteChannelReply(id: Id): Promise<void>;                                            // mine: out of the group
  channelReplyMod(id: Id, ok: boolean, again?: boolean): Promise<void>;                 // held: out or removed; live: kept or taken down; again: a lost send, re-sent
  channelReplyRestore(id: Id): Promise<void>;                                           // a take-down undone
  mapFlaw(f: { ver: string; floor: number; u: number; v: number; px: number; py: number; body: string }): Promise<void>; // a long press on the map
  mapFlaws(): Promise<{ id: Id; ver: string; floor: number; u: number; v: number; px: number | null; py: number | null; body: string; at: Ts; done: Ts | null }[]>; // the admin
  mapFlawsMine(): Promise<{ id: Id; ver: string; floor: number; u: number; v: number; px: number | null; py: number | null; body: string }[]>; // my own open ones, pins on the map
  mapFlawDone(id: Id, done: boolean): Promise<void>;
  assistant(q: string, history: { role: 'user' | 'assistant'; text: string }[], context?: { kind: 'event' | 'club'; id: Id }): Promise<AssistReply>; // the students' assistant; context: the card it was asked from (the server reads its facts)
  assistantVote(mark: string, vote: 'up' | 'down'): Promise<void>; // 👍/👎 on an answer's signed topic
  assistantSend(mark: string, pair: string, q: string, a: string): Promise<void>; // on 👎, the student's own tap: this one signed question and answer, no name
  eventFill(org: Id, text: string): Promise<{ title?: string; date?: string; start?: string; end?: string; place?: string; description?: string; price?: number }>; // a new event from its announcement (AI)
  qrCheckin(p: string): Promise<{ title: string; done: boolean; left?: boolean }>;                    // a scan of the big screen's QR (ci_…): done = counted, else waits for my sign-up
  screens(): Promise<import('./types').ScreenSession[]>;                               // the check-in sessions I run (/show)
  bindScreen(code: string, session?: Id): Promise<import('./types').ScreenSession>;   // a scan of /show's pairing QR (sh_…); conflict/pick: say which session
  screenAct(id: Id, act: 'start' | 'finish' | 'unpair' | 'out' | 'in'): Promise<import('./types').ScreenSession>; // out/in: the QR marks leaving or arriving
  screenGrant(id: Id, code: string): Promise<{ granted: number; batch: string }>;  // the owner: an award to everyone counted (Admin → Awards); undoBatch(batch)
  eventScreen(event: Id): Promise<import('./types').ScreenSession>;                   // an event's own session, made on first use (organizers)
  screenCsv(id: Id): Promise<{ url: string; name: string }>;                          // a short-lived link for Telegram's download
  takenDown(): Promise<TakenDown[]>;                                                 // admin: the last 30 days' take-downs
  restore(target: TakenDown['target'], id: Id): Promise<void>;                       // admin: undo one
  resolveReport(target: ReportItem['target'], id: Id, remove: boolean, abuse?: boolean, rule?: TgcRule): Promise<void>; // admin: take it down or leave it (a Telegram comment: the terms clause it broke, or the reports were abuse)
  tgcClosed(): Promise<TgcClosed[]>;                                                 // admin: whose Telegram /report is closed
  tgcReopen(user: Id): Promise<void>;                                                // admin: give it back
  tgComment(): Promise<TgComment | null>;                                            // my own deleted Telegram comment, to me alone
  myClubApplication(): Promise<ClubApplication | null>;  // starting a club (§4.6): my latest application
  applyClub(input: ClubApplicationInput): Promise<ClubApplication>;
  clubApplications(): Promise<ClubApplication[]>;         // admin: pending first
  decideClubApplication(id: Id, approve: boolean, reason?: string): Promise<ClubApplication>;
  officialPath(org: Id): Promise<OfficialPath | null>;   // the club's team: the Ascent's checklist (null: official already)
  askOfficial(org: Id): Promise<OfficialPath | null>;    // its President or a Vice, at the top: asks DMP for the ✓
  decideOfficial(id: Id, approve: boolean, reason?: string): Promise<OfficialRequest>; // admin
  feature(postId: Id, days: number): Promise<Post>;      // admin: on top of List for everyone; 0 ends it
  /** Admin → Awards: give a person a manual award (the bot sends them its card); undo: ungrant(its id) */
  giveGrant(userId: Id, code: GrantItem['code']): Promise<GrantItem>;
  /** the scanner: a person's card QR is one grant; `run` names this opening of the camera for undoBatch('s_' + run) */
  grantScan(qr: string, code: GrantItem['code'], run?: string): Promise<GrantItem>;
  /** undo one of my grants, at any time */
  ungrant(id: Id): Promise<void>;
  /** undo a scanner run ('s_…'), a link's people ('l_' + token), a check-in session's (screenGrant's batch) */
  undoBatch(batch: string): Promise<{ undone: number }>;
  /** a manual award back off a person, at any time (a mistake): every grant of it */
  takeBackGrant(userId: Id, code: GrantItem['code']): Promise<import('./types').BadgeHolder>;
  /** Admin → Awards' rows: how many hold each award (a badge once a person); who holds one, newest first */
  awardCounts(): Promise<Record<string, number>>;
  awardPeople(award: string): Promise<GrantItem[]>;
  /** one person's manual awards (the chips) */
  awardsOf(userId: Id): Promise<import('./types').BadgeHolder>;
  /** my award links of the last 30 days, live first, with who used each; revoke stops one now */
  grantLinks(): Promise<import('./types').GrantLink[]>;
  revokeLink(token: string): Promise<void>;
  /** find a student with their manual awards; the owner's check-in sessions */
  badgePeople(q: string): Promise<import('./types').BadgeHolder[]>;
  badgeSessions(): Promise<import('./types').BadgeSession[]>;
  useGrantLink(token: string): Promise<{ code: string }>;
  /** Admin → Awards → Show QR: open one for an award, its current code (closing it: revokeLink); a student's scan of it */
  openBadgeQr(code: GrantItem['code']): Promise<import('./types').BadgeQr>;
  badgeQr(token: string): Promise<import('./types').BadgeQr>;
  claimBadgeQr(p: string): Promise<{ code: string }>;
  myGrants(): Promise<GrantItem[]>;
  staff(): Promise<Staff>;                                // admin: the app's team and the banned
  staffFind(username: string): Promise<StaffRow>;          // admin: anyone who opened the app, by @username
  staffSearch(q: string): Promise<StaffRow[]>;
  search(q: string): Promise<{ events: EventCard[]; clubs: OrgRef[] }>; // the one search: by any name, what I may see (the admin: all)
  staffMutes(): Promise<import('./types').StaffMute[]>;   // staff: my work-item notifications
  setStaffMute(kind: string, on: boolean): Promise<import('./types').StaffMute[]>;                 // admin → People: by name, @username, student ID or id
  inbox(): Promise<import('./types').Inbox>;               // staff: everything waiting, and what was done lately
  undoDone(id: Id): Promise<void>;                         // a Done row taken back (each undo keeps its own rules)
  adminDeleteEvent(id: Id): Promise<void>;                 // admin: hidden now, gone in a day (Undo till then)
  adminRestoreEvent(id: Id): Promise<void>;
  setStaff(userId: Id, role: PlatformRole): Promise<Staff>; // admin role: the owner only
  ban(userId: Id, on: boolean, reason?: string): Promise<Staff>; // a reason to ban (he sees it)
  audit(): Promise<AuditRow[]>;                            // the owner: the last 200 actions done with power
  adminStats(): Promise<AdminStats>;
  adminDay(day: number): Promise<AdminDay>;
  adminAi(): Promise<AdminAi>;
  aiRetry(): Promise<void>;
  chats(): Promise<Chats>;                                // the chats directory (§4.11)
  /** any chat suggested from the app: @name, a t.me link or an invite link */
  suggestChat(link: string): Promise<{ status: 'sent' | 'waiting' | 'exists' | 'org' | 'limit' | 'later' | 'slow' | 'notchat' | 'bad'; title: string }>;
  chatOpened(id: Id): Promise<void>;                      // the tick
  addChat(input: { title: string; url: string; kind: Chat['kind']; school: string | null; course: number | null }): Promise<Chat>; // moderators, admin
  deleteChat(id: Id): Promise<void>;                      // a suggestion declined too
  approveChat(id: Id): Promise<Chat>;                     // a suggested chat into the catalog
  setChatOrg(id: Id, org: Id | null): Promise<Chat>;      // the admin: whose a catalog chat is (PLAN 86)
  setChatSection(id: Id, section: ChatSection): Promise<Chat>; // staff: what a chat is for (the AI's mark goes)
  orgChats(org: Id): Promise<StudioChat[]>;               // Vice+ (and the admin): the org's chats in Studio
  addOrgChat(org: Id, link: string): Promise<StudioChat[]>; // @name, t.me link or invite link; bad_input notchat, conflict taken / limit, unavailable
  mainOrgChat(org: Id, chat: Id): Promise<StudioChat[]>;  // a public channel only
  dropOrgChat(org: Id, chat: Id): Promise<StudioChat[]>;
  mirrorOrgChat(org: Id, chat: Id, on: boolean): Promise<StudioChat[]>;
  rosterSeen(): Promise<void>;                            // PLAN 95: the join toasts shown
  rosterClaim(row: Id): Promise<void>;                    // "Yes, it's me" on a row under another name
  rosterRequests(org?: Id): Promise<RosterRequest[]>;             // the claims I confirm (President; DMP for a club without one)
  rosterDecide(row: Id, ok: boolean): Promise<void>; // the main channel's posts in the club's news
  registry(back?: number): Promise<RegistryOrg[]>;       // DMP Head+ and the admin (§4.13); a month `back` months ago (0–12)
  registryRoster(org: Id): Promise<RosterMember[]>;
  /** DMP Head+ (and the admin) give a club the ✓ or take it back; its President hears it from the bot */
  setOfficial(org: Id, on: boolean): Promise<OrgRef>;
  registryMemos(): Promise<SentMemo[]>;                   // the memos clubs marked sent in the last 7 days
  registrySearch(q: string): Promise<RegistryHit[]>;      // a club member by name or student ID
  registryExport(): Promise<void>;                        // every roster as a CSV into my chat with the bot
  markUnlocked(code: string, level: number): Promise<{ unlocked: Me['unlocked'] }>; // the unlock moment was shown
  anthemHeard(): Promise<{ unlocked: Me['unlocked'] }>; // the anthem heard start to finish without skipping: its award (once)
  calendarFeed(): Promise<{ page: string; feed: string }>;     // my events in the phone's calendar (a kept secret address)
  resetCalendar(): Promise<void>;                              // the old address stops; the next calendarFeed() makes a new one
  eventInvites(id: Id): Promise<FriendInvite[]>;               // "Bring a friend": my friends and where they stand
  inviteFriend(id: Id, userId: Id): Promise<FriendInvite[]>;    // the bot brings them our card; once per friend and event
  addAlbumPhoto(id: Id, file: Blob): Promise<EventFull>;        // the guests' album (canAddPhotos); re-encoded like a cover
  removeAlbumPhoto(id: Id, photo: Id): Promise<EventFull>;      // mine, or any as the club's Head+
  uploadPhoto(file: Blob): Promise<Media>;                       // Head+; re-encoded by the server, use its id as coverId
  uploadVideo(file: Blob, progress: (done: number) => void, wide?: boolean): Promise<Video>; // Head+; in pieces, then compressed: its id as videoId (wide: wideVideoId)
  video(id: Id): Promise<Video>;                                 // my upload, while it is compressed
  // Vice+: applications and whether the club takes them
  joinRequests(org: Id): Promise<JoinRequest[]>;
  // the club's own team (SPEC §2, the rank rule): Vice+ manage people below them, the President hands the club over
  team(org: Id): Promise<TeamMember[]>;
  /** everyone in a club or school, as anyone sees them (403 when the club hides the list) */
  people(org: Id): Promise<Member[]>;
  // the club's invite link (§4.5, Vice+): the same token until replaced; a student who opens it is a Member at once
  invite(org: Id, dept?: Id): Promise<{ token: string }>;   // dept: the newcomer lands in that department
  teamLink(org: Id): Promise<{ token: string; expiresAt: Ts }>; // the link for the whole team, 7 days: the live one, else a new one
  teamLinkOff(org: Id): Promise<void>;
  acceptInvite(token: string): Promise<Org>;
  removeMember(org: Id, user: Id): Promise<void>;          // my own id = leave; a President: conflict/'president'
  transfer(org: Id, user: Id): Promise<TeamMember[]>;
  // Team 2.0 (§2b): the club's own roles (Vice+) and tags (Head+), probation, removal by request, bans
  teamSetup(org: Id): Promise<TeamSetup>;
  saveRole(org: Id, input: { name: string; tr?: Partial<Record<'ru' | 'kk' | 'en', string>>; color: string; rights: Right[] }, id?: Id): Promise<TeamSetup>;  // conflict/'taken'
  deleteRole(org: Id, id: Id): Promise<TeamSetup>;
  assignRole(org: Id, id: Id, users: Id[]): Promise<{ team: TeamMember[]; setup: TeamSetup; skipped: number }>; // ticked get it, the rest lose it
  saveTag(org: Id, input: { name: string; color: string; department?: boolean }, id?: Id): Promise<TeamSetup>;
  deleteTag(org: Id, id: Id): Promise<TeamSetup>;
  updateMember(org: Id, user: Id, patch: MemberPatch): Promise<TeamMember[]>;
  removeFromClub(org: Id, user: Id, ban: boolean, note: string): Promise<{ done: boolean }>; // a Head's: a request (done: false)
  decideRemoval(id: Id, approve: boolean): Promise<void>;
  unban(org: Id, user: Id): Promise<void>;
  decideJoin(id: Id, accept: boolean): Promise<void>;
  setRecruiting(org: Id, on: boolean): Promise<Org>;
  /** the club's profile (Vice+): name, letters, emoji, cover, about, links */
  updateOrg(org: Id, patch: OrgPatch): Promise<Org>;
  deleteOrg(org: Id): Promise<void>;                            // the President's own empty club (made by mistake)
  shortLinks(org: Id): Promise<ShortLink[]>;                                   // Vice+
  addShortLink(org: Id, link: { slug: string; kind: ShortLink['kind']; eventId?: Id }): Promise<ShortLink[]>; // conflict 'taken' / 'limit'
  dropShortLink(slug: string): Promise<void>;                                  // the club's Vice+, or the admin revoking it

}

export const api: Api = server;
