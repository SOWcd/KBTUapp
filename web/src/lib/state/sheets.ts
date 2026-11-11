// Openers for the sheets that are reachable from anywhere (any avatar opens the profile card, any
// event row opens the event). App wires them up; components call these, so no import cycles.
import type { AlbumPhoto, AttendeeReceipt, Chat, EventCard, EventFull, GrantItem, Id, LinkCard, MemoAsks, OrgCategory, OrgRef, PersonCard, Post, Round, RosterSpot, ScreenSession } from '../api';
import type { Manual, ShelfItem } from '../awards';
import type { AskCtx } from './assistant.svelte';
import type { StoryGroup } from '../posts';

// wait: ms before "ok" can be tapped (a second confirm, so a double tap doesn't go through both)
export type Ask = { title: string; text?: string; ok: string; cancel: string; danger?: boolean; wait?: number };

/** a still copy of the top capsule and its theme wrapper's classes (the map's circle cuts between it and the live one) */
export type CapCopy = { node: HTMLElement; theme: string };
export function copyCap(): CapCopy | null {
  const c = document.querySelector<HTMLElement>('.cap');
  if (!c) return null;
  const node = c.cloneNode(true) as HTMLElement;
  node.removeAttribute('role');
  return { node, theme: c.parentElement?.className ?? '' };
}
/** where the map was opened from (the nav's round button): it opens out of that circle and closes back into it, and
 *  the capsule as it was before the map changed it */
export const mapFrom: { at: { x: number; y: number; r: number } | null; cap: CapCopy | null } = { at: null, cap: null };

/** The registration mode's half last used (scanner or QR): the row opens there, no extra tap. */
export function doorMode(mode?: 'scan' | 'qr'): 'scan' | 'qr' {
  try { if (mode) localStorage.setItem('door.mode', mode); return localStorage.getItem('door.mode') === 'qr' ? 'qr' : 'scan'; } catch { return mode ?? 'scan'; }
}

/** The registration mode (owner, Nov 10): the door scanner and the event's QR on this phone, one switch apart, opened
 *  where it was left. A member's QR: an ordinary public event only, never the volunteers ledger's club `vol` (server
 *  checkin._guests: those scans count hours and misses), so there the scanner has no switch. runs: its organizers. */
export function registration(e: EventCard, runs: boolean, vol?: Id): void {
  const qr = !e.guestHost && (runs || (!e.meeting && e.visibility !== 'members' && e.visibility !== 'leaders' && e.org.id !== vol));
  if (qr && doorMode() === 'qr') sheets.eventQr(e.id, true); else sheets.scanner(e.id, false, qr);
}

export const sheets = {
  /** invite: opened by their invite link r_<code> (its landing: "Add as a friend", one tap) */
  person: (_id: Id, _invite?: { code: string; card: LinkCard }) => {},
  /** my QR full screen (the corner of my badge) */
  myQr: (_link: string, _p: PersonCard) => {},
  /** Admin → Awards → Show QR: the award's rotating code full screen, for the hall's cameras */
  badgeQr: (_award: Manual, _code: GrantItem['code']) => {},
  /** a new photo of me (or a club logo) framed in a rounded square; the square crop, or null when cancelled */
  cropPhoto: (_file: Blob): Promise<Blob | null> => Promise.resolve(null),
  club: (_id: Id) => {},
  /** `from`: the tapped poster, which grows into the sheet's header; `album`: its guests' album opened over it (the bot's ph_) */
  event: (_id: Id, _from?: Element | null, _album?: boolean) => {},
  /** the event sheet for an unsaved editor form: what students will see */
  preview: (_e: EventFull) => {},
  ticket: (_id: Id) => {},
  pay: (_id: Id) => {},                 // a held seat of a paid event: the Kaspi details and the receipt (§4.3)
  receipt: (_r: AttendeeReceipt, _name: string, _ondone?: () => void) => {},  // the organizer's look at one receipt
  /** an album full screen, from photo `start`; `onremove` takes one out and answers with what is left */
  //   from: the thumbnail it grows out of and shrinks back into (one element, or one per photo: the grid's, the mosaic's)
  photos: (_photos: AlbumPhoto[], _start: number, _onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>, _ongone?: (p: AlbumPhoto) => void, _from?: Element | ((p: AlbumPhoto) => Element | null | undefined)) => {},
  /** every photo of an album at once, a grid as in the phone's Photos (live: `list` and `adding` are read as they change) */
  album: (_list: () => AlbumPhoto[], _onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>, _ongone?: (p: AlbumPhoto) => void, _add?: () => void, _adding?: () => number, _look?: { title: string; note?: string }) => {},
  /** my chosen photos into the Gallery: the preview, where to, Publish (GALLERY) */
  galleryAdd: (_files: File[]) => {},
  login: (_after?: () => void, _lock?: boolean) => {},
  // Studio (lazy chunks): the event editor (new when no id), the door scanner, the attendee list
  editor: (_org: Id, _id?: Id) => {},
  scanner: (_id: Id, _names?: boolean, _qr?: boolean) => {}, // names: a club's own event, marked by name (no tickets); qr: its switch to the event's QR (EventQr)
  // only: a scanner-only door helper (server crew.py): tickets, no list by name
  scannerOnly: (_id: Id) => {},
  crew: (_id: Id, _onchange?: (n: number) => void) => {},
  /** a club's volunteers ledger (server logic/vol.py): the list (its President and whom she grants), one volunteer (mine: my own) */
  /** appeals to the Student Government: the composer and my appeals; one of mine; SG's queue and one appeal in it */
  appeals: () => {},
  myAppeal: (_id: Id) => {},
  sgQueue: () => {},
  sgAppeal: (_id: Id) => {},
  volLedger: () => {},
  volPerson: (_id: Id, _mine?: boolean) => {}, // an event's door helpers (a running club's President or Vice)
  attendees: (_id: Id) => {},
  assistant: (_ctx?: AskCtx) => {},      // the students' assistant (with the forum's switch); ctx: asked from that card
  mapFlaws: () => {},                    // the admin: the map's flaws marked with a long press
  /** an event's rotating check-in QR full screen on the organizer's own phone, no laptop */
  eventQr: (_event: Id, _door?: boolean) => {}, // door: the registration mode's other half, its switch back to the scanner
  /** the same screen for someone an organizer let help (server checkin.py); scanner: the event's door scanner too */
  helperQr: (_session: Id, _event: Id | null, _scanner: boolean) => {},
  /** the QR an organizer shows to let someone help */
  handQr: (_session: Id) => {},
  screens: (_code?: string, _event?: Id, _seed?: ScreenSession) => {}, // /show: pair a laptop's screen (its sh_ QR) and run the check-in; event: its own session; seed: that session alone (the capsule)
  /** Profile's "Big screen": the scanner for a computer's pairing QR; a helper's own QR */
  bigScreen: () => {},
  /** Studio → an event: the organizer's screen (money, people, tools) */
  manage: (_id: Id, _staff?: boolean) => {},
  /** next week's memo to DMP for a club (Head+): from Studio and the bot's Wednesday message */
  memo: (_org: Id) => {},
  /** the clubs' rosters (PLAN 95): the claims I confirm */
  rosterRequests: (_ondone?: () => void, _org?: number) => {},
  /** one memo item (a room, guests...) without an event, dated from the memo's week `from`; `oninsert` takes its text */
  /** an event's volunteer applications (the organizers) */
  volunteers: (_id: Id, _need: number) => {},
  memoItem: (_org: Id, _kind: keyof MemoAsks, _from: number, _oninsert: (text: string) => void) => {},
  /** casting (a club's recruitment round): a student's application; the team's setup and board */
  roundApply: (_org: Id, _source?: string) => {},
  roundSetup: (_org: Id, _round?: Round | null, _onsaved?: () => void) => {},
  roundBoard: (_org: Id) => {},
  // a club's applications (Vice+) and its "taking applications" switch
  joinInbox: (_org: Id) => {},
  /** always-open applications: the club's own questions (Vice+), and a student's answers to them */
  joinQuestions: (_org: Id) => {},
  joinApply: (_org: Id) => {},
  /** Team 2.0 (§2b): the club's roles and tags (Vice+ / Head+ make them), its bans (Vice+); `onchange` after an edit */
  teamSetup: (_org: Id, _onchange?: () => void) => {},
  /** removing someone below me: a Vice+ at once, a Head's as a request (`request`); a ban if wanted */
  removeMember: (_org: Id, _user: Id, _name: string, _request: boolean, _ondone?: (done: boolean) => void) => {},
  /** the pages pushed from the settings under my lanyard (Me): about me, notifications, my name, privacy and its pages, about */
  settings: (_kind: 'me' | 'notify' | 'name' | 'privacy' | 'phone' | 'city' | 'school' | 'course' | 'last' | 'first' | 'middle' | 'sees' | 'about' | 'donate') => {},
  /** the admin panel (pilot): clubs and their teams */
  admin: () => {},
  /** the campus map, on a floor (step 1: the 2023 plans) */
  map: (_place?: string, _exit?: boolean) => {}, // exit: "Help me get out" (the startapp=exit link); a place with a room ("Aud. 305", a class's "251"): its floor, the room circled
  /** delete account: what goes, then the KBTU password again */
  deleteAccount: (_lost: { awards: number; tickets: number; clubs: number }) => {},
  /** the server says the policy changed (a refused write): the fresh /api/me raises the gate (ConsentGate) */
  consent: () => {},
  /** news as stories (Afisha's List, a club's page): the clubs' posts full screen, from club `start` */
  stories: (_groups: StoryGroup[], _start?: number, _at?: number) => {},
  /** what used to be a tab's other pages (Oct 30: one tab, one screen): every post (Afisha's "All"), the Feed full screen
   *  (Afisha's "In a row"), my friends (Profile's row), my club's team (My club's row) */
  news: () => {},
  feed: () => {},
  friends: () => {},
  team: () => {},
  /** a new post for a club (Head+), from Studio */
  composer: (_org: Id, _post?: Post, _casting?: boolean) => {},
  /** add a friend: my one-time QR and link, or a request by @username; 'share' opens Telegram's share picker at once */
  addFriend: (_mode?: 'share') => {},
  /** a new achievement level just earned in a sheet that stays open (the anthem's): its unlock moment now, over it */
  celebrate: () => {},
  /** my invite link (referrals): its QR, or sent as our bot's card */
  referral: (_code: string) => {},
  /** DMP's registry: a club's roster; the whole registry in a sheet (for the admin) */
  roster: (_org: OrgRef, _onofficial?: (on: boolean) => void) => {},
  /** the club's profile (Vice+): name, letters, emoji, cover, about, links */
  clubEdit: (_org: Id, _at?: 'chats') => {},
  /** everyone in a club or school (the club sheet's "All members") */
  people: (_org: Id, _title: string) => {},
  /** starting a club (§4.6): my application or the form */
  createClub: () => {},
  /** KBTU's academic calendar: the year's dates (SPEC §4.11) */
  academic: () => {},
  /** KBTU's anthem to listen to and learn: Afisha's card until the Oct 31 initiation, Profile's row, startapp=anthem */
  anthem: () => {},
  /** my whole award collection and the showcase picker (Profile: the badge's numbers) */
  awards: () => {},
  /** Admin → Awards: give a manual award to a person, by the scanner, by a link, to a check-in's people */
  adminAwards: () => {},
  /** the two older award sheets' names: both open Admin → Awards now */
  give: () => {},
  badges: () => {},
  /** Admin → Clubs and schools; at: that club opened in the list (Admin's search) */
  adminClubs: (_at?: Id) => {},
  adminChats: () => {},
  /** the forum channel's moderation: held posts, this week's live and taken-down ones, the owner's reveal */
  adminForum: () => {},
  /** a club of mine: its Studio pushed over the Clubs tab (the tab's Mine row, the bot's links) */
  studio: (_org: Id) => {},
  /** all my clubs as rows (the Clubs tab's "All" circle, 3+ of them); role: mine there (a club I only follow: null) */
  clubList: (_view: 'all' | 'schools' | 'quiet' | OrgCategory) => {},
  myClubs: (_rows: { org: OrgRef; role: string | null; sub: string }[], _title?: string) => {},
  /** how my week gets into the app: the portal's page saved and sent to the bot (first: right after the sign-in) */
  schedHowTo: () => {},
  /** my whole week of classes */
  week: () => {},
  /** the forum (F1 find people), a request opened in it */
  forum: (_ask?: Id) => {},
  forumSkills: (_onsaved?: () => void) => {},
  newAsk: (_onmade?: () => void) => {},
  /** a new post to the forum channel (the Forum tab's plus); draft: the words back after a refused send */
  /** my anonymous post: a reply in its comments through the bot, and how my replies stand */
  channelReply: (_post: { id: Id; body: string }) => {},
  askPeople: (_ask: Id, _title: string) => {},
  /** every chat of the directory */
  chats: (_chats: Chat[]) => {},
  /** the AI page in Admin: the translator's state and work */
  adminAi: () => {},
  /** the owner's audit log */
  adminAudit: () => {},
  /** suggest any chat for the catalog: paste @name or a link */
  suggestChat: () => {},
  registry: () => {},
  /** comments under a post or an event; `onchange` hears the new count */
  comments: (_kind: 'post' | 'event', _id: Id, _title: string, _onchange?: (n: number) => void) => {},
  /** the one report sheet: `about` names the thing, `onsent` hears it went (a photo hides for me) */
  report: (_target: 'comment' | 'post' | 'event' | 'user' | 'photo' | 'ask' | 'fpost', _id: Id, _about?: string, _onsent?: () => void) => {},
  /** "Bring a friend" to an event */
  invite: (_id: Id, _title: string) => {},
  /** "Bring a friend" from their card: my upcoming events */
  inviteTo: (_id: Id, _name: string) => {},
  /** one achievement or badge up close */
  /** an award up close; `mine` adds Share */
  award: (_it: ShelfItem, _mine?: boolean) => {},
  /** In-app confirmation (never a system dialog); resolves true on "ok". */
  ask: (_q: Ask): Promise<boolean> => Promise.resolve(false),
  /** the same with a few words to write (a meeting's "Can't make it": why); null = cancelled. tel: a phone number instead,
   *  handed over as +7XXXXXXXXXX; value: filled in to edit; line: one line, Enter answers (a nick) */
  askText: (_q: Ask & { placeholder: string; max: number; tel?: boolean; value?: string; line?: boolean }): Promise<string | null> => Promise.resolve(null),
  answers: (_title: string, _questions: import('../api').Question[]): Promise<{ q: string; a: string }[] | null> => Promise.resolve(null), // an event's own questions at sign-up
};
