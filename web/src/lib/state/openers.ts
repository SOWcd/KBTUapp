// The sheets' openers, each written once (sheets.ts holds `sheets`; this fills it as it loads, App imports it first), and
// the deep links' table. Every sheet is its own chunk: a dynamic import here, never a static one.
import type { Component } from 'svelte';
import { api, ApiErr, type AlbumPhoto, type AttendeeReceipt, type Chat, type ClubTag, type EventBracket, type EventFull, type EventGroups, type GrantItem, type Id, type MemoAsks, type MyCheckin, type OrgRef, type PersonCard, type Post, type Question, type ResearchSurvey, type Round, type ScreenSession, type TeamMember, type TeamPick, type TeamSetup } from '../api';
import { achItem, type Manual, type ShelfItem } from '../awards';
import { t } from '../i18n/index.svelte';
import { warmMap } from '../map';
import { may } from '../perms';
import type { StoryGroup } from '../posts';
import { count, type Screen } from '../stats';
import { setTeamConsent } from '../teamConsent';
import { haptic, inTelegram, tgTry } from '../tg';
import { burst } from '../../ui/burst';
import { channel } from './channel.svelte';
import { data, eventDetails, keepRef, loadAfisha, loadMyCard, loadResearch, loadResearchRequests } from './data.svelte';
import { asStudent, loadMe, runningCheckin, session } from './session.svelte';
import { sheets, type InviteLanding, type SheetKey } from './sheets';
import { loadSubjects } from './subjects.svelte';
import { open, say, ui } from './ui.svelte';

// A sheet in its own chunk needs the network the first time: offline, taps used to queue and all open on top of each
// other once it was back. Now only the latest tap opens, and after 2 s the app says there's no network.
let want = 0;
// a chunk already loaded opens in the tap's own task: import() resolves a task later even then
const loaded = new Map<() => Promise<unknown>, { default: Component<any> }>();
// (the promise settles once it's open or given up: a queued moment waits for it, lib/moments.ts)
export function lazy<P extends Record<string, unknown>>(load: () => Promise<{ default: Component<P> }>, props: Omit<P, 'overlay'>, stat?: Screen, key?: SheetKey | null): Promise<void> {
  if (session.revoked || session.banned) return Promise.resolve();
  const mine = ++want, got = loaded.get(load);
  if (got) { open(got.default, props, stat, key); return Promise.resolve(); }
  const slow = setTimeout(() => { if (mine === want) say(t('common.offline'), 'pleading_face_3d'); }, 2000);
  return load().then((m) => { clearTimeout(slow); loaded.set(load, m); if (mine === want && !session.revoked && !session.banned) open(m.default, props, stat, key); }).catch(() => { clearTimeout(slow); if (mine === want) say(t('common.offline'), 'pleading_face_3d'); });
}
/** the account closed (banned, revoked): a sheet still loading opens nothing */
export const dropLazy = () => { want++; };
/** a chunk fetched ahead, so its sheet opens in the tap's frame */
export const warm = (load: () => Promise<{ default: Component<any> }>) => void load().then((m) => loaded.set(load, m)).catch(() => {});
// named, so a chunk is kept once loaded and opens in the tap's frame (an arrow made here each call never was): lazy()'s
// cache is keyed by them, and App warms them ahead
export const chunks = {
  // the event, person and club sheets are chunks warmed during startup so subsequent taps open in the same frame
  event: () => import('../../screens/sheets/EventSheet.svelte'),
  person: () => import('../../screens/sheets/PersonSheet.svelte'),
  club: () => import('../../screens/sheets/ClubSheet.svelte'),
  ticket: () => import('../../screens/sheets/TicketView.svelte'), // the ticket brings the QR encoder: its own chunk, fetched once the app is idle
  stories: () => import('../../screens/sheets/Stories.svelte'),
  photos: () => import('../../screens/sheets/PhotoViewer.svelte'),
  album: () => import('../../screens/sheets/AlbumGrid.svelte'),
  gallery: () => import('../../screens/afisha/Gallery.svelte'),
  // a club's Studio is for its members only: its page and views are their own chunks
  studio: () => import('../../screens/club/StudioPane.svelte'),
  team: () => import('../../screens/club/Team.svelte'),
  // what used to be pages beside a tab's screen: warmed ahead, so their sheets open in the tap's frame
  feed: () => import('../../screens/afisha/Feed.svelte'),
  news: () => import('../../screens/afisha/News.svelte'),
  friends: () => import('../../screens/profile/Friends.svelte'),
  people: () => import('../../screens/profile/People.svelte'),
  screen: () => import('../../screens/club/ScreenSheet.svelte'),
  research: () => import('../../screens/forum/Research.svelte'),
  researchForm: () => import('../../screens/forum/ResearchForm.svelte'),
  researchPropose: () => import('../../screens/forum/ResearchPropose.svelte'),
  help: () => import('../../screens/profile/HelpSheet.svelte'),
  feedback: () => import('../../screens/profile/FeedbackSheet.svelte'),
  voices: () => import('../../screens/admin/AdminVoices.svelte'),
  admin: () => import('../../screens/admin/AdminSheet.svelte'),
};

const asResearchStudent = (action: () => void) => asStudent(() => {
  const student = session.me?.student;
  if (!student || student.manual || student.studentId.startsWith('staff') || student.consent === 'staff') {
    say(t('research.studentOnly'), 'warning_3d');
    return;
  }
  action();
}, 'research');

// a round with nothing to answer or pick (round.quick): one tap sends it, no confirm (owner, Nov 3); the button turns
// "Sent" at once, the toast says what the club sees, with an Undo (it withdraws). Anything else, or a sent one, opens the sheet
async function quickApply(org: Id, source = 'club') {
  const sheet = () => lazy(() => import('../../screens/sheets/RoundApply.svelte'), { org, source });
  const o = data.orgs.find((x) => x.id === org);
  if (!o?.round?.quick || o.round.applied) return sheet();
  const round = o.round, mark = (applied: boolean) => { const x = data.orgs.find((y) => y.id === org); if (x?.round?.id === round.id) x.round = { ...x.round, applied }; };
  mark(true); haptic.ok();
  try {
    await api.applyRound(round.id, { departments: [], answers: {}, source });
    count('do.casting');
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

/** a running check-in's controls: the organizer's sheet, a helper's own QR (so a closed one needs no second scan) */
export function openCheckin(c: MyCheckin): void {
  haptic.tap();
  if (c.helper) sheets.helperQr(c.session, c.event, c.scanner); else sheets.screens(undefined, undefined, c);
}

export const openers = {
  /** invite: opened by their invite link r_<code> (its landing: "Add as a friend", one tap) */
  person: (id: Id, invite?: InviteLanding) => lazy(chunks.person, { id, invite }, 'sheet.person', invite ? `invite:${id}:${invite.code}` : id),
  /** my QR full screen (the corner of my badge) */
  myQr: (link: string, p: PersonCard) => lazy(() => import('../../screens/profile/MyQr.svelte'), { link, p }),
  /** Admin → Awards → Show QR: the award's rotating code full screen, for the hall's cameras */
  badgeQr: (award: Manual, code: GrantItem['code']) => lazy(() => import('../../screens/admin/BadgeQr.svelte'), { award, code }),
  /** a new photo of me (or a club logo) framed in a rounded square; the square crop, or null when cancelled */
  cropPhoto: (file: Blob): Promise<Blob | null> => new Promise((done) => lazy(() => import('../../screens/profile/PhotoCrop.svelte'), { file, done })),
  club: (id: Id) => lazy(chunks.club, { id }, 'sheet.club', id),
  /** `from`: the tapped poster, which grows into the sheet's header; `album`: its guests' album opened over it (the bot's ph_) */
  event: (id: Id, from?: Element | null, album?: boolean) => lazy(chunks.event, { id, from, album }, 'sheet.event', album ? `album:${id}` : id),
  /** the event sheet for an unsaved editor form: what students will see */
  preview: (e: EventFull) => lazy(chunks.event, { id: e.id, preview: e }, undefined, `preview:${e.id}`),
  /** a saved draft as students will see it once it's published: the editor's preview of the draft as the server has it */
  draftPreview: (id: Id): void => void api.event(id).then((e) => sheets.preview({ ...e, status: 'published' }), () => say(t('common.error'), 'warning_3d')),
  ticket: (id: Id) => lazy(chunks.ticket, { id }, 'sheet.ticket'),
  pay: (id: Id) => lazy(() => import('../../screens/sheets/PaySheet.svelte'), { id }), // a held seat of a paid event: the Kaspi details and the receipt (§4.3)
  receipt: (receipt: AttendeeReceipt, name: string, ondone?: () => void) => lazy(() => import('../../screens/club/ReceiptSheet.svelte'), { receipt, name, ondone }), // the organizer's look at one receipt
  /** an album full screen, from photo `start`; `onremove` takes one out and answers with what is left */
  //   from: the thumbnail it grows out of and shrinks back into (one element, or one per photo: the grid's, the mosaic's)
  photos: (photos: AlbumPhoto[], start: number, onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>, ongone?: (p: AlbumPhoto) => void, from?: Element | ((p: AlbumPhoto) => Element | null | undefined)) =>
    lazy(chunks.photos, { photos, start, onremove, ongone, from }),
  /** every photo of an album at once, a grid as in the phone's Photos (live: `list` and `adding` are read as they change) */
  album: (list: () => AlbumPhoto[], onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>, ongone?: (p: AlbumPhoto) => void, add?: () => void, adding?: () => number) =>
    lazy(chunks.album, { list, onremove, ongone, add, adding }),
  /** the Gallery: the albums' strip and every photo by place, one "+" to add mine */
  gallery: () => lazy(chunks.gallery, {}),
  // Studio (lazy chunks): the event editor (new when no id), the door scanner, the attendee list
  editor: (org: Id, id?: Id, staff?: boolean) => lazy(() => import('../../screens/club/EventEditor.svelte'), { org, id, staff }, 'sheet.editor', id == null ? null : `${org}:${id}:${!!staff}`), // staff: Admin's "an event for a club"
  // names: a club's own event, marked by name (no tickets); qr: the door screen, its switch to the event's QR
  scanner: (id: Id, names?: boolean, qr?: boolean, ondone?: () => void) => lazy(() => import('../../screens/club/Scanner.svelte'), { id, names, qr, ondone }, 'sheet.scanner', `${id}:${!!names}:${!!qr}`),
  // only: a scanner-only door helper (server crew.py): tickets, no list by name (the Mark screen, no lists)
  scannerOnly: (id: Id) => lazy(() => import('../../screens/club/Scanner.svelte'), { id, qr: true, only: true }, 'sheet.scanner', `only:${id}`),
  crew: (id: Id, onchange?: (n: number) => void) => lazy(() => import('../../screens/club/CrewSheet.svelte'), { id, onchange }),
  /** a club's report after its event (server evreports.py, REPORTS); org: the co-host's own (the host's without it) */
  eventReport: (id: Id, org?: Id) => lazy(() => import('../../screens/club/EventReport.svelte'), { id, org }, undefined, org == null ? id : `${id}:${org}`),
  /** a club's volunteers ledger (server logic/vol.py): the list (its President and whom she grants), one volunteer (mine: my own) */
  /** appeals to the Student Government: the composer and my appeals; one of mine; SG's queue and one appeal in it */
  appeals: () => asStudent(() => lazy(() => import('../../screens/appeals/Appeals.svelte'), {})),
  myAppeal: (id: Id) => lazy(() => import('../../screens/appeals/MyAppeal.svelte'), { id }),
  sgQueue: () => lazy(() => import('../../screens/appeals/SgQueue.svelte'), {}),
  sgAppeal: (id: Id) => lazy(() => import('../../screens/appeals/SgAppeal.svelte'), { id }),
  /** the help desk: the composer with KRI's question in it (sent only on the student's tap) and my questions; one of mine; its queue and one question in it */
  askHuman: (q?: string) => asStudent(() => lazy(() => import('../../screens/appeals/Appeals.svelte'), { desk: 'help', q })),
  myAsk: (id: Id) => lazy(() => import('../../screens/appeals/MyAppeal.svelte'), { id, desk: 'help' }, undefined, `help:${id}`),
  helpQueue: () => lazy(() => import('../../screens/appeals/SgQueue.svelte'), { desk: 'help' }),
  helpAppeal: (id: Id) => lazy(() => import('../../screens/appeals/SgAppeal.svelte'), { id, desk: 'help' }, undefined, `help:${id}`),
  // vol: these close together when the ledger is no longer mine to see (data.svelte.ts volGone)
  volLedger: () => lazy(() => import('../../screens/club/VolLedger.svelte'), { vol: true }),
  volDoor: (sid: Id, title: string) => lazy(() => import('../../screens/club/VolDoor.svelte'), { sid, title }), // a session's door: who left without checking out, the hand-over link
  volPerson: (id: Id, mine?: boolean) => lazy(() => import('../../screens/club/VolPerson.svelte'), { id, mine, vol: true }, undefined, mine ? `mine:${id}` : id), // an event's door helpers (a running club's President or Vice)
  attendees: (id: Id) => lazy(() => import('../../screens/club/Attendees.svelte'), { id }, 'sheet.attendees'),
  /** the Mark screen's «People»: the team by department and the guests, came / not came, marked by hand; onchange after a mark */
  doorPeople: (id: Id, onchange?: () => void, guestsOnly?: boolean) => lazy(() => import('../../screens/club/People.svelte'), { id, onchange, guestsOnly }, 'sheet.doorpeople', `${id}:${!!guestsOnly}`),
  /** Studio's «Guest list»: the organizers' file, its preview and save, the door's list as a CSV */
  guestList: (id: Id) => lazy(() => import('../../screens/club/GuestList.svelte'), { id }, undefined, String(id)),
  /** Secret Santa's chat: one thread of my pair ('to': I am the Santa of `name`; 'from': with my own Santa) */
  santaChat: (event: Id, side: 'to' | 'from', name?: string) => lazy(() => import('../../screens/sheets/SantaChat.svelte'), { event, side, name }, undefined, `santa-${event}-${side}`),
  santaReports: () => lazy(() => import('../../screens/admin/SantaReports.svelte'), {}), // the staff: reported Secret Santa chats
  mapFlaws: () => lazy(() => import('../../screens/admin/MapFlaws.svelte'), {}),         // the admin: the map's flaws marked with a long press
  /** an event's rotating check-in QR full screen on the organizer's own phone, no laptop */
  eventQr: (event: Id) => lazy(() => import('../../screens/club/EventQr.svelte'), { event }),
  /** the same screen for someone an organizer let help (server checkin.py); scanner: the event's door scanner too */
  // a helper lands on the same Mark screen as the organizer (owner, Nov 14: helpers didn't know where to go); no scanner of the event: its QR alone
  helperQr: (sess: Id, event: Id | null, scanner: boolean) => (event && scanner ? lazy(() => import('../../screens/club/Scanner.svelte'), { id: event, qr: true, sess, only: true }, 'sheet.scanner', `session:${sess}`)
    : lazy(() => import('../../screens/club/EventQr.svelte'), { sess, event, scanner })),
  /** the QR an organizer shows to let someone help */
  handQr: (sess: Id) => lazy(() => import('../../screens/club/EventQr.svelte'), { sess, hand: true }),
  // /show: pair a laptop's screen (its sh_ QR) and run the check-in; event: its own session; seed: that session alone (the capsule); org: the page from that club's Studio; crew: an event's team, made and started
  screens: (code?: string, event?: Id, seed?: ScreenSession, org?: Id, crew?: Id) => lazy(chunks.screen, { code, event, seed, org, crew }),
  /** Profile's "Big screen": my sessions first (start one, connect a laptop's /show from there: ScreenSheet); a helper's own QR */
  bigScreen: (): void => {
    if (session.me?.bigScreen !== 'pair') { // a helper has no screen to pair (only a session's organizers may: server checkin.bind): their QR
      const c = runningCheckin();
      if (c) openCheckin(c); else { say(t('scr.helpEnded'), 'waving_hand_3d_default'); void loadMe(true); }
      return;
    }
    haptic.tap(); sheets.screens();
  },
  /** Studio → an event: the organizer's screen (money, people, tools); org: a co-host's Studio (its report alone) */
  manage: (id: Id, staff?: boolean, org?: Id) => lazy(() => import('../../screens/club/EventManage.svelte'), { id, staff, org }, 'sheet.manage', `${id}:${!!staff}:${org ?? ''}`),
  /** next week's memo to DMP for a club (Head+): from Studio and the bot's Wednesday message */
  memo: (org: Id) => lazy(() => import('../../screens/club/MemoSheet.svelte'), { org }),
  /** the clubs' rosters (PLAN 95): the claims I confirm */
  rosterRequests: (ondone?: () => void, org?: number) => lazy(() => import('../../screens/club/RosterRequests.svelte'), { ondone, org }),
  /** an event's volunteer applications (the organizers) */
  volunteers: (id: Id, need: number) => lazy(() => import('../../screens/club/VolunteersSheet.svelte'), { id, need }),
  /** one memo item (a room, guests...) without an event, dated from the memo's week `from`; `oninsert` takes its text */
  memoItem: (org: Id, kind: keyof MemoAsks, from: number, oninsert: (text: string) => void) => lazy(() => import('../../screens/club/MemoItemSheet.svelte'), { org, kind, from, oninsert }),
  /** casting (a club's recruitment round): a student's application; the team's setup and board */
  // actions, not views: a guest is asked to sign in first, then lands in the sheet (owner, Oct 23: B1, a guest filled
  // in a whole application before the server said no)
  roundApply: (org: Id, source?: string) => asStudent(() => void quickApply(org, source), `rc_${org}`),
  roundSetup: (org: Id, round?: Round | null, onsaved?: () => void) => lazy(() => import('../../screens/club/RoundSetup.svelte'), { org, round, onsaved }),
  roundBoard: (org: Id) => lazy(() => import('../../screens/club/RoundBoard.svelte'), { org }),
  /** Made together: the screen (at 'support': opened at its Support section); my own "name me?" sheet */
  credits: (at?: 'support') => lazy(chunks.people, { at }),
  creditAsk: () => lazy(() => import('../../screens/profile/CreditAsk.svelte'), {}),
  /** students make the app: the ways to help and the signed offer; what is wrong (anonymous or in Telegram); the admin's list of both */
  helpUs: () => asStudent(() => lazy(chunks.help, {})),
  feedback: () => asStudent(() => lazy(chunks.feedback, {})),
  adminVoices: () => lazy(chunks.voices, {}),
  research: () => { void loadResearch(); void lazy(chunks.research, {}); },
  researchForm: (survey: ResearchSurvey) => asResearchStudent(() => void lazy(chunks.researchForm, { survey })),
  researchPropose: () => asResearchStudent(() => void lazy(chunks.researchPropose, {})),
  adminResearch: () => { void loadResearchRequests(); void lazy(() => import('../../screens/admin/AdminResearch.svelte'), {}); },
  /** Secret Santa's welcome over Studio (the bot's sn_, Studio's row): how it works and the one start */
  santaHi: (org: Id) => lazy(() => import('../../screens/club/SantaHi.svelte'), { org }),
  // a club's applications (Vice+) and its "taking applications" switch
  joinInbox: (org: Id) => lazy(() => import('../../screens/club/JoinInbox.svelte'), { org }, 'sheet.joininbox'),
  /** always-open applications: the club's own questions (Vice+), and a student's answers to them */
  joinQuestions: (org: Id) => lazy(() => import('../../screens/club/JoinQuestions.svelte'), { org }),
  joinApply: (org: Id) => lazy(() => import('../../screens/sheets/JoinApply.svelte'), { org }),
  /** Team 2.0 (§2b): the club's roles and tags (Vice+ / Head+ make them), its bans (Vice+); `onchange` after an edit */
  teamSetup: (org: Id, onchange?: () => void) => lazy(() => import('../../screens/club/TeamSetupSheet.svelte'), { org, onchange }),
  /** one person of a club's Team, their own sheet over it: roles, departments, probation, hand-over, removal */
  member: (org: Id, user: Id, setup: () => TeamSetup | null, depts: (x: TeamMember) => ClubTag[], onchange: () => void) =>
    lazy(() => import('../../screens/club/MemberSheet.svelte'), { org, user, setup, depts, onchange }, 'sheet.member'),
  /** removing someone below me: a Vice+ at once, a Head's as a request (`request`); a ban if wanted */
  removeMember: (org: Id, user: Id, name: string, request: boolean, ondone?: (done: boolean) => void) =>
    lazy(() => import('../../screens/club/RemoveSheet.svelte'), { org, user, name, request, ondone }),
  /** the pages pushed from the settings under my lanyard (Me): about me, notifications, my name, privacy and its pages, about */
  settings: (kind: 'app' | 'me' | 'notify' | 'name' | 'privacy' | 'phone' | 'city' | 'school' | 'course' | 'last' | 'first' | 'middle' | 'sees' | 'about' | 'donate') => {
    if (kind === 'donate') count('do.donate');
    return lazy(() => import('../../screens/profile/SettingsSheet.svelte'), { kind });
  },
  /** the admin panel (pilot): clubs and their teams */
  admin: () => lazy(chunks.admin, {}),
  /** the campus map, on a floor (step 1: the 2023 plans) */
  // exit: "Help me get out" (the startapp=exit link); a place with a room ("Aud. 305", a class's "251"): its floor, the room circled
  map: (place?: string, exit?: boolean) => { warmMap(); return lazy(() => import('../../screens/map/CampusMap.svelte'), { place, exit }, 'sheet.map'); },
  /** delete account: what goes, then the KBTU password again */
  deleteAccount: (lost: { awards: number; tickets: number; clubs: number }) => lazy(() => import('../../screens/profile/DeleteSheet.svelte'), { lost }),
  /** news as stories (Afisha's List, a club's page): the clubs' posts full screen, from club `start` */
  stories: (groups: StoryGroup[], start?: number, at?: number) => lazy(chunks.stories, { groups, start, at }),
  /** a tab's other pages (one tab, one screen): every post (Afisha's "All"), the Feed full screen
   *  (Afisha's "In a row"), my friends (Profile's row), my club's team (My club's row) */
  news: () => lazy(chunks.news, {}, 'sheet.news'),
  feed: () => lazy(chunks.feed, {}, 'sheet.feed'),
  friends: () => lazy(chunks.friends, {}, 'sheet.friends'),
  team: (at?: Id) => lazy(chunks.team, { at }, 'sheet.team'),  // at: that person's actions open (Studio's Roles and admins)
  /** a new post for a club (Head+), from Studio */
  composer: (org: Id, post?: Post, casting?: boolean) => lazy(() => import('../../screens/club/PostComposer.svelte'), { org, post, casting }),
  /** add a friend: my one-time QR and link, or a request by @username; 'share' opens Telegram's share picker at once */
  addFriend: (mode?: 'share') => lazy(() => import('../../screens/profile/AddFriend.svelte'), { share: mode === 'share' }),
  /** my invite link (referrals): its QR, or sent as our bot's card */
  referral: (code: string) => lazy(() => import('../../screens/profile/RefSheet.svelte'), { code }),
  /** DMP's registry: a club's roster; the whole registry in a sheet (for the admin) */
  roster: (org: OrgRef, onofficial?: (on: boolean) => void) => lazy(() => import('../../screens/dmp/Roster.svelte'), { org, onofficial }),
  /** the club's profile (Vice+): name, letters, emoji, cover, about, links */
  clubEdit: (org: Id, at?: 'chats') => lazy(() => import('../../screens/club/ClubEditSheet.svelte'), { id: org, at }, undefined, at ? `${at}:${org}` : org),
  /** everyone in a club or school (the club sheet's "All members") */
  people: (org: Id, title: string) => lazy(() => import('../../screens/sheets/PeopleSheet.svelte'), { org, title }),
  /** starting a club (§4.6): my application or the form */
  createClub: () => lazy(() => import('../../screens/sheets/CreateClubSheet.svelte'), {}),
  /** KBTU's academic calendar: the year's dates (SPEC §4.11) */
  academic: () => lazy(() => import('../../screens/sheets/AcademicSheet.svelte'), {}),
  /** KBTU's anthem to listen to and learn: Profile's row, startapp=anthem */
  anthem: () => lazy(() => import('../../screens/sheets/AnthemSheet.svelte'), {}),
  /** my whole award collection and the showcase picker (Profile: the badge's numbers) */
  awards: () => lazy(() => import('../../screens/profile/AwardsSheet.svelte'), {}, 'sheet.awards'),
  /** Admin → Clubs and schools: every organization by name */
  adminClubs: () => lazy(() => import('../../screens/admin/AdminClubs.svelte'), {}),
  adminChats: () => lazy(() => import('../../screens/admin/AdminChats.svelte'), {}),
  /** the forum channel's moderation: held posts, this week's live and taken-down ones, the owner's reveal */
  adminForum: () => lazy(() => import('../../screens/admin/AdminForum.svelte'), {}),
  /** a club of mine: its Studio pushed over the Clubs tab (the tab's Mine row, the bot's links) */
  studio: (org: Id, asCreator?: boolean) => lazy(chunks.studio, { org, asCreator }, 'sheet.studio', asCreator ? `creator:${org}` : org),
  /** how my week gets into the app: the portal's page saved and sent to the bot (first: right after the sign-in) */
  schedHowTo: () => lazy(() => import('../../screens/sheets/ScheduleHowTo.svelte'), {}),
  /** my whole week of classes */
  week: () => lazy(() => import('../../screens/sheets/WeekSheet.svelte'), {}, 'sheet.week'),
  /** the subjects' cards: the list with its search; one subject's card (who's looking for study partners) */
  subjects: () => asStudent(() => { void loadSubjects(true); return lazy(() => import('../../screens/subjects/Subjects.svelte'), {}); }),
  subject: (id: string) => asStudent(() => { void loadSubjects(); return lazy(() => import('../../screens/subjects/Subject.svelte'), { id }); }),
  /** the forum (F1 find people), a request opened in it */
  forum: (ask?: Id) => lazy(() => import('../../screens/forum/Forum.svelte'), { ask }),
  forumSkills: (onsaved?: () => void) => lazy(() => import('../../screens/forum/SkillsSheet.svelte'), { onsaved }),
  newAsk: (onmade?: () => void) => lazy(() => import('../../screens/forum/NewAsk.svelte'), { onmade }),
  /** a new post to the forum channel (the Forum tab's plus); draft: the words back after a refused send */
  /** my anonymous post: a reply in its comments through the bot, and how my replies stand */
  channelReply: (post: { id: Id; body: string }) => lazy(() => import('../../screens/forum/ChannelReply.svelte'), { post }),
  /** a channel post's comments, written and read in the app; link: the same thread in Telegram, for the rest */
  channelThread: (post: { id: Id; body: string; mine: boolean; anon: boolean; link: string }) => lazy(() => import('../../screens/forum/ChannelThread.svelte'), { post }),
  askPeople: (ask: Id, title: string) => lazy(() => import('../../screens/forum/AskPeople.svelte'), { ask, title }),
  /** every chat of the directory */
  chats: (chats: Chat[]) => lazy(() => import('../../screens/sheets/ChatsSheet.svelte'), { chats }),
  /** the AI page in Admin: the translator's state and work */
  adminAi: () => lazy(() => import('../../screens/admin/AdminAi.svelte'), {}),
  /** the creator's private donation receipts */
  adminDonations: () => lazy(() => import('../../screens/admin/AdminDonations.svelte'), {}),
  /** the owner's audit log */
  adminAudit: () => lazy(() => import('../../screens/admin/AdminAudit.svelte'), {}),
  /** suggest any chat for the catalog: paste @name or a link */
  suggestChat: () => lazy(() => import('../../screens/sheets/SuggestChat.svelte'), {}),
  /** DMP's tree of every organisation's groups */
  dmpChats: () => lazy(() => import('../../screens/dmp/ChatsTree.svelte'), {}),
  /** comments under a post or an event; `onchange` hears the new count */
  comments: (kind: 'post' | 'event', id: Id, title: string, onchange?: (n: number) => void) => lazy(() => import('../../screens/sheets/CommentsSheet.svelte'),
    { kind, id, title, onchange }, 'sheet.comments', `${kind}:${id}`),
  /** the one report sheet: `about` names the thing, `onsent` hears it went (a photo hides for me) */
  report: (target: 'comment' | 'post' | 'event' | 'user' | 'photo' | 'ask' | 'fpost', id: Id, about?: string, onsent?: () => void) =>
    asStudent(() => lazy(() => import('../../screens/sheets/ReportSheet.svelte'), { target, id, about, onsent }, undefined, `${target}:${id}`)),
  /** "Bring a friend" to an event */
  invite: (id: Id, title: string) => lazy(() => import('../../screens/sheets/InviteSheet.svelte'), { id, title }),
  /** "Bring a friend" from their card: my upcoming events */
  inviteTo: (id: Id, name: string) => asStudent(() => lazy(() => import('../../screens/sheets/InviteToSheet.svelte'), { id, name })),
  /** one achievement or badge up close */
  /** an award up close; `mine` adds Share */
  award: (it: ShelfItem, mine?: boolean) => lazy(() => import('../../screens/sheets/AwardSheet.svelte'), { it, mine }),
  // an event's own questions at sign-up
  answers: (title: string, questions: Question[]): Promise<{ q: string; a: string }[] | null> => new Promise((done) => lazy(() => import('../../screens/sheets/AnswersSheet.svelte'), { title, questions, done })),
  /** a team event's sign-up: make a team (its name) or "I have no team"; null: closed, no sign-up (server evteams.py) */
  teamPick: (title: string, min: number, max: number): Promise<TeamPick | 'solo' | null> => new Promise((done) => lazy(() => import('../../screens/sheets/TeamPickSheet.svelte'), { title, min, max, done })),
  /** a captain's invite link (startapp=et_<token>): the team, one tap to join */
  teamInvite: (token: string) => asStudent(() => lazy(() => import('../../screens/sheets/TeamInviteSheet.svelte'), { token }), `et_${token}`),
  /** the organizer's teams: every team, those with none, Form teams */
  teams: (id: Id) => lazy(() => import('../../screens/club/TeamsSheet.svelte'), { id }),
  bracket: (id: Id, manage: boolean, seed: EventBracket, onchange: (b: EventBracket) => void) =>
    lazy(() => import('../../screens/sheets/BracketSheet.svelte'), { id, manage, seed, onchange }, undefined, `${id}:${!!manage}`),
  /** a team event's group stage: the tables and matches for everyone; manage: the organizers' draw and scores; seed: already loaded; onchange: the opener's copy follows */
  groups: (id: Id, manage?: boolean, seed?: EventGroups, onchange?: (g: EventGroups) => void, replacesBracket?: boolean) =>
    lazy(() => import('../../screens/sheets/GroupsSheet.svelte'), { id, manage, seed, onchange, replacesBracket }, undefined, `${id}:${!!manage}:${!!replacesBracket}`),
};
Object.assign(sheets, openers);

// ---- deep links `<prefix>_<arg>` (startapp=): one table, prefix -> its opener. App.deepLink asks it after the plain
// words (donate, map, ask, ...); here, out of App, so a test runs every link through it (openers.test.ts) ----
/** what only App has: its own steps for a few links */
export type AppLinks = {
  join: (org: number, token: string) => void;
  president: (org: number, token: string) => void;
  msBack: (force?: boolean) => void;
  checkIn: (p: string) => void;
  helpRun: (p: string) => void;
  takeDoor: (token: string) => void;
};
/** open: gets the arg's groups; student: a guest signs in first (asStudent); arg: what follows `<prefix>_` (an id by default) */
type Link = [open: (...g: string[]) => unknown, student?: boolean, arg?: RegExp];
const ID = /^(\d+)$/;
const REF = /^(\d+)(?:_([A-Z2-7]{10}))?$/; // an id, and a member's "My link" (ev_) or a profile QR's code (u_) after it

/** `p` opened by its prefix's opener; false: no prefix here takes it. afterSignIn: deepLink run again after the sign-in */
export function openDeepLink(p: string, app: AppLinks, afterSignIn = false): boolean {
  // tm_<club>: the bot's removal messages open that club's Team (§2b) over its Studio; no longer in it: the club's page
  // (the Team once the Studio pane is open: two chunk loads at once, lazy() opens only the later one, and Team reads
  // ui.club, which the pane sets: a cold start opened another club's Team, no Studio under it)
  const team = (org: number) => {
    if (!session.me?.memberships.some((x) => x.org.id === org)) { sheets.club(org); return; }
    ui.tab = 'club'; ui.club = org; void lazy(chunks.studio, { org }, 'sheet.studio').then(() => sheets.team());
  };
  // st_<club>: the bot's "host an event with us": that club's Studio, whose To do answers it
  const studio = (org: number) => {
    if (!session.me?.memberships.some((x) => x.org.id === org)) { sheets.club(org); return; }
    ui.tab = 'club'; ui.club = org; void lazy(chunks.studio, { org }, 'sheet.studio');
  };
  // sn_<club>: the bot's Secret Santa announcement: that club's Studio and over it the game's welcome; no longer one
  // who may start it (a stale link): the Studio alone, or the club's page (as st_)
  const santaHi = (org: number) => {
    const mm = session.me?.memberships.find((x) => x.org.id === org);
    if (!may(mm, 'events')) { studio(org); return; }
    ui.tab = 'club'; ui.club = org; void lazy(chunks.studio, { org }, 'sheet.studio').then(() => sheets.santaHi(org));
  };
  const table: Record<string, Link> = {
    join: [(org, token) => app.join(Number(org), token), false, /^(\d+)_([0-9a-f]{24})$/], // a club's invite link (§4.5)
    pres: [(org, token) => app.president(Number(org), token), false, /^(\d+)_([0-9a-f]{24})$/], // a new club's one-time President link (the admin's, §2)
    gl: [(code) => { // the creator's award link (one-time, or many's: admin claim new)
      ui.tab = 'profile';
      asStudent(async () => {
        try { await api.useGrantLink(code); await loadMe(); void loadMyCard(); haptic.ok(); } // loadMe brings the unlock moment
        catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'conflict' ? t('give.already') : t('give.linkDead'), 'pleading_face_3d'); } // mine already: the link stays for whom it was meant
      }, p); // a guest's Microsoft sign-in round trip keeps the link (takeAgain)
    }, false, /^([0-9a-f]{24})$/],
    bq: [() => { // Admin → Awards → Show QR: the giver's rotating code (logic/profiles.py claim_qr)
      ui.tab = 'profile';
      asStudent(async () => {
        try { await api.claimBadgeQr(p); await loadMe(); void loadMyCard(); haptic.ok(); } // loadMe brings the unlock moment
        catch (e) { haptic.error(); say(!(e instanceof ApiErr) ? t('common.error') : e.code === 'conflict' ? t('give.already') : e.message === 'qr_old' ? t('ci.old') : t('give.linkDead'), 'pleading_face_3d'); }
      }, p);
    }, false, /^[0-9a-f]{24}_\d{1,12}_[0-9a-f]{16}$/],
    gq: [(token) => asStudent(async () => { // a club group's join request (its guard bot): signed up, let in
      try { await api.guardJoin(token); haptic.ok(); say(t('guard.in'), 'party_popper_3d'); setTimeout(() => tgTry((w) => w.close()), 1800); }
      catch { haptic.error(); say(t('guard.late'), 'pleading_face_3d'); }
    }, p), false, /^([A-Za-z0-9_-]+\.[0-9a-f]{24})$/],
    // back from the Microsoft sign-in (/ms.html): it lands only on the Telegram that started it; then what the guest
    // wanted before Microsoft (a door scan: shown counted) runs after the student ID, as msBack's. A second launch by
    // the same link (ms.html's button after its own redirect) finds the claim taken: no error then
    ...(inTelegram && { ms: [(code) => void api.msClaim(code).then(() => true, () => false).then(async (ok) => {
      await loadMe();
      if (!ok && !session.me?.msPending && !session.me?.student?.ms) { haptic.error(); say(t('common.error'), 'pleading_face_3d'); return; }
      haptic.ok();
      if (ok && session.me?.student?.ms) say(t('login.msDone'), 'sparkles_3d');
      if (ok || session.me?.msPending) app.msBack(true);
    }), false, /^([\w-]{24})$/] satisfies Link }),
    // the bot: SG answered this appeal: its own view, the answer on top
    apl: [(id) => { ui.tab = session.channel ? 'forum' : 'profile'; if (session.me?.appeals) sheets.myAppeal(Number(id)); }],
    // the bot: a person answered my question: its own view, the answer on top
    ask: [(id) => { ui.tab = 'profile'; if (session.me?.ask) sheets.myAsk(Number(id)); }],
    // the bot's "photos are in the album" / "add yours": the event, its album open over it. The sheet opens the album
    // itself once its details are in (it used to be a second fetch and a second lazy() here, which any other sheet
    // opening meanwhile silently dropped: only the latest lazy() opens)
    ph: [(id) => sheets.event(Number(id), null, true)],
    cp: [(id) => sheets.comments('post', Number(id), t('cm.title')), true], // the bot's "someone replied" under a post: its thread
    // the bot's question / answer card: the event and its thread
    cm: [(s) => { const id = Number(s); sheets.event(id); asStudent(() => { api.event(id).then((e) => sheets.comments('event', id, e.title)).catch(() => {}); }); }],
    aw: [(code) => { // someone's award card: my own way to the same one
      ui.tab = 'profile';
      asStudent(async () => {
        sheets.awards();
        // an older card may name a badge's variant (aw_init26f): its badge
        const a = (await api.person(session.me!.id)).awards.achievements.find((x) => x.code === code || x.variants?.some((v) => v.code === code));
        if (a) sheets.award(achItem(a), a.level > 0);
      });
    }, false, /^([a-z0-9_]{1,40})$/],
    ci: [() => void app.checkIn(p), false, /^\d+_\d+_[0-9a-f]{16}$/], // the big screen's QR (server checkin.py)
    hq: [() => asStudent(() => void app.helpRun(p), p), false, /^\d+_\d+_\d+_[0-9a-f]{16}$/], // an organizer's "help me mark people" QR
    et: [(token) => sheets.teamInvite(token), false, /^([0-9a-f]{24})$/], // a captain's invite to their team at an event (server evteams.invite)
    // the volunteers ledger's hand-over link: that session's door, mine to run (server vol.take)
    vh: [(token) => asStudent(() => void app.takeDoor(token), p), false, /^([0-9a-f]{32})$/],
    meet: [(id) => {
      ui.tab = 'club';
      asStudent(async () => {
        try { const s = await api.meetupSession(Number(id)); sheets.screens(undefined, undefined, s, s.org ?? undefined); }
        catch { say(t('scr.notYours'), 'warning_3d'); }
      }, p);
    }],
    sh: [(code) => sheets.screens(code), true, /^([0-9a-f]{16})$/], // /show's pairing QR: only a session's organizers bind it
    // the bot's first comment under a post: the Forum tab, that post in view (bare fp: the tab)
    fp: [(id) => { channel.focus = id ? Number(id) : null; if (session.channel) ui.tab = 'forum'; }, false, /^(\d+)?$/],
    sj: [(id) => sheets.subject(id), false, /^([0-9a-f]{10})$/], // the bot: my listing on a subject was hidden: its card
    fa: [(id) => sheets.forum(Number(id)), true], // the bot's ping or "your request is hidden": the forum, that request in sight
    // someone's invite link (Nov 2: the one link): noted for them as a referral, and their card with "Add as a friend"
    // (opening adds nobody); my own: nothing
    r: [(code) => {
      void api.refer(code).catch(() => {});
      api.linkCard(code).then((card) => {
        if (card.friendship !== 'self') sheets.person(card.person.id, { code, card, alreadyRegistered: card.registered && !afterSignIn });
      })
        .catch(() => say(t('fr.linkDead'), 'pleading_face_3d'));
    }, false, /^([A-Z2-7]{10})$/],
    ce: [(id) => sheets.clubEdit(Number(id), 'chats'), true], // the bot's "chat linked to your club": Studio's chats, for "show posts in the feed"
    rc: [(id) => sheets.roundApply(Number(id), 'link'), true], // a club's recruitment round: a shared card, the bot's "X is recruiting"
    iv: [(id) => sheets.roundApply(Number(id), 'bot'), true], // the bot's "pick an interview time" and its reminders
    // the bot's "agree to teams": the event with the teams consent sheet over it (the sheet over the event, not under it)
    tc: [(id) => void lazy(chunks.event, { id: Number(id) }, 'sheet.event').then(() => setTeamConsent(true)), true],
    memo: [(id) => sheets.memo(Number(id)), true], // the bot's Wednesday "next week's memo is ready"
    // ev_<id>_<ref>: a club member's "My link": the sign-up goes to them
    ev: [(id, ref) => { if (ref) keepRef(Number(id), ref); sheets.event(Number(id)); }, false, REF],
    tk: [(id) => sheets.ticket(Number(id)), false, REF],
    cl: [(id) => sheets.club(Number(id)), false, REF],
    jr: [(id) => sheets.joinInbox(Number(id)), false, REF],
    // u_<id>_<code>: someone's profile QR (the invite sheet shows it too): noted for them as an invite
    u: [(id, code) => { if (code) void api.refer(`${id}_${code}`).catch(() => {}); sheets.person(Number(id)); }, false, REF],
    tm: [(id) => team(Number(id)), false, REF],
    st: [(id) => studio(Number(id)), false, REF],
    sn: [(id) => santaHi(Number(id)), false, REF],
    // mg_<event>: the bot's "a member asks to come as a guest": the event's organizer screen, its asks on top
    mg: [(s) => { const ev = Number(s); asStudent(() => { void eventDetails(ev).then(() => sheets.manage(ev), () => sheets.event(ev)); }); }, false, REF],
  };
  const [, prefix, rest = ''] = p.match(/^([a-z]+)(?:_(.+))?$/) ?? []; // bare: an empty arg (fp)
  const link = prefix && Object.prototype.hasOwnProperty.call(table, prefix) ? table[prefix] : null;
  const g = link && rest.match(link[2] ?? ID);
  if (!link || !g) return false;
  const open = () => link[0](...g.slice(1));
  if (link[1]) asStudent(open); else open();
  return true;
}
