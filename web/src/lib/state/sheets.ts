// Openers for the sheets that are reachable from anywhere (any avatar opens the profile card, any
// event row opens the event). App wires them up; components call these, so no import cycles.
import type { AlbumPhoto, AttendeeReceipt, Chat, EventFull, Id, MemoAsks, OrgRef, PersonCard, Post, Round, RosterSpot } from '../api';
import type { ShelfItem } from '../awards';
import type { StoryGroup } from '../posts';

export type Ask = { title: string; text?: string; ok: string; cancel: string; danger?: boolean };

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
export const mapFrom: { at: { x: number; y: number } | null; cap: CapCopy | null } = { at: null, cap: null };

export const sheets = {
  person: (_id: Id) => {},
  /** my QR full screen (the corner of my badge) */
  myQr: (_link: string, _p: PersonCard) => {},
  club: (_id: Id) => {},
  /** `from`: the tapped poster, which grows into the sheet's header */
  event: (_id: Id, _from?: Element | null) => {},
  /** the event sheet for an unsaved editor form: what students will see */
  preview: (_e: EventFull) => {},
  ticket: (_id: Id) => {},
  pay: (_id: Id) => {},                 // a held seat of a paid event: the Kaspi details and the receipt (§4.3)
  receipt: (_r: AttendeeReceipt, _name: string, _ondone?: () => void) => {},  // the organizer's look at one receipt
  /** an album full screen, from photo `start`; `onremove` takes one out and answers with what is left */
  photos: (_photos: AlbumPhoto[], _start: number, _onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>, _ongone?: (p: AlbumPhoto) => void) => {},
  login: (_after?: () => void) => {},
  // Studio (lazy chunks): the event editor (new when no id), the door scanner, the attendee list
  editor: (_org: Id, _id?: Id) => {},
  scanner: (_id: Id, _names?: boolean) => {}, // names: a club's own event, marked by name (no tickets)
  attendees: (_id: Id) => {},
  /** Studio → an event: the organizer's screen (money, people, tools) */
  manage: (_id: Id) => {},
  /** next week's memo to DMP for a club (Head+): from Studio and the bot's Wednesday message */
  memo: (_org: Id) => {},
  /** the clubs' rosters (PLAN 95): the welcome before the KBTU sign-in, a row under another name, the claims I confirm */
  rosterWelcome: (_spots: RosterSpot[]) => {},
  rosterAsk: (_row: RosterSpot & { id: Id; dept: string | null }) => {},
  rosterRequests: (_ondone?: () => void) => {},
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
  /** Team 2.0 (§2b): the club's roles and tags (Vice+ / Head+ make them), its bans (Vice+); `onchange` after an edit */
  teamSetup: (_org: Id, _onchange?: () => void) => {},
  /** removing someone below me: a Vice+ at once, a Head's as a request (`request`); a ban if wanted */
  removeMember: (_org: Id, _user: Id, _name: string, _request: boolean, _ondone?: (done: boolean) => void) => {},
  /** my nickname and photo (Telegram's or my own), from Me and my badge's photo */
  look: () => {},
  /** behind the Settings page's rows: About the app (who sees what), power saving */
  settings: (_kind: 'privacy' | 'power') => {},
  /** the admin panel (pilot): clubs and their teams */
  admin: () => {},
  /** the campus map, on a floor (step 1: the 2023 plans) */
  map: (_place?: string, _exit?: boolean) => {}, // exit: "Help me get out" (the startapp=exit link); a place with a room ("Aud. 305", a class's "251"): its floor, the room circled
  /** delete account: what goes, then the KBTU password again */
  deleteAccount: (_lost: { awards: number; tickets: number; clubs: number }) => {},
  /** a new privacy policy version: agree once more (lib/legal.ts) */
  consent: () => {},
  /** news as stories (Afisha's List, a club's page): the clubs' posts full screen, from club `start` */
  stories: (_groups: StoryGroup[], _start?: number, _at?: number) => {},
  /** a new post for a club (Head+), from Studio */
  composer: (_org: Id, _post?: Post) => {},
  /** add a friend: my one-time QR and link, or a request by @username; 'share' opens Telegram's share picker at once */
  addFriend: (_mode?: 'share') => {},
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
  /** my whole award collection and the showcase picker (Profile: the badge's numbers) */
  awards: () => {},
  /** the creator's own awards (the admin panel): a QR scanner each, "Bug hunter" a one-time link */
  give: () => {},
  adminClubs: () => {},
  adminChats: () => {},
  /** every club, the biggest first (the Clubs tab's "All clubs · N") */
  allClubs: () => {},
  /** how my week gets into the app: the portal's page saved and sent to the bot (first: right after the sign-in) */
  schedHowTo: (_first?: boolean) => {},
  /** my whole week of classes */
  week: () => {},
  /** the forum (F1 find people), a request opened in it */
  forum: (_ask?: Id) => {},
  forumSkills: (_onsaved?: () => void) => {},
  newAsk: (_onmade?: () => void) => {},
  askPeople: (_ask: Id, _title: string) => {},
  /** every chat of the directory */
  chats: (_chats: Chat[]) => {},
  /** the AI page in Admin: the translator's state and work */
  adminAi: () => {},
  /** the app's team: roles and bans (admin); the audit log */
  adminTeam: () => {},
  adminAudit: () => {},
  /** suggest any chat for the catalog: paste @name or a link */
  suggestChat: () => {},
  registry: () => {},
  /** comments under a post or an event; `onchange` hears the new count */
  comments: (_kind: 'post' | 'event', _id: Id, _title: string, _onchange?: (n: number) => void) => {},
  /** the one report sheet: `about` names the thing, `onsent` hears it went (a photo hides for me) */
  report: (_target: 'comment' | 'post' | 'event' | 'user' | 'photo' | 'ask', _id: Id, _about?: string, _onsent?: () => void) => {},
  /** "Bring a friend" to an event */
  invite: (_id: Id, _title: string) => {},
  /** "Bring a friend" from their card: my upcoming events */
  inviteTo: (_id: Id, _name: string) => {},
  /** one achievement or badge up close */
  /** an award up close; `mine` adds Share */
  award: (_it: ShelfItem, _mine?: boolean) => {},
  /** In-app confirmation (never a system dialog); resolves true on "ok". */
  /** a computer: the app is made for phones (once, until "continue") */
  pc: (_ok: () => void) => {},
  ask: (_q: Ask): Promise<boolean> => Promise.resolve(false),
  /** the same with a few words to write (a meeting's "Can't make it": why); null = cancelled. tel: a phone number instead,
   *  handed over as +7XXXXXXXXXX */
  askText: (_q: Ask & { placeholder: string; max: number; tel?: boolean }): Promise<string | null> => Promise.resolve(null),
};
