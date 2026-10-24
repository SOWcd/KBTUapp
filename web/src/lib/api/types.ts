// The API contract (SPEC §6), as the server (server/kbtu) answers it: screens only ever see these shapes. JSON fields are camelCase; time is unix seconds (UTC).

export type Id = number;
export type Ts = number;
export type Lang = 'ru' | 'kk' | 'en';
export type OrgRole = 'member' | 'head' | 'vice' | 'president';
export type PlatformRole = 'user' | 'moderator' | 'admin';
export type OrgKind = 'club' | 'school' | 'council' | 'office' | 'app';

export interface ApiError { error: 'need_student' | 'forbidden' | 'not_found' | 'full' | 'closed' | 'conflict' | 'rate_limited' | 'bad_input' | 'unavailable'; message?: string }

/** Image prepared by the server: WebP, thumbnail and a tiny inline blur preview. */
/** An application to start a club (§4.6): it opens after the creator's check. `applicant` for moderators and the admin. */
export interface ClubApplication {
  id: Id; name: string; short: string; description: string; emoji: string; cover: number; links: string[]; why: string | null;
  status: 'pending' | 'approved' | 'rejected'; reason: string | null; orgId: Id | null; createdAt: Ts; decidedAt: Ts | null; reapplyAt: Ts | null;
  applicant?: { person: PersonRef; fullName: string; username: string | null; course: number | null; school: string | null } | null;
}
export interface ClubApplicationInput { name: string; short: string; description: string; emoji: string; cover: number; link?: string | null; why?: string; links?: string[] }

/** A curated Telegram chat (§4.11): for everyone, or aimed at a school and/or a course; a tick once I've opened it. */
export interface Chat { id: Id; title: string; kind: 'channel' | 'group' | 'forum'; url: string; members: number | null; photo: string | null /* from its t.me page */; school: string | null; course: number | null; opened: boolean }
export interface Chats { forYou: Chat[]; all: Chat[]; pending?: (Chat & { at: Ts })[] /* admins and moderators: suggested, waiting */ }

/** DMP's view of a club member (§3, §4.13): contacts only of Presidents and Vices. */
export interface DmpPerson { person: PersonRef; fullName: string; studentId: string; course: number | null; school: string | null; username: string | null; email: string | null; phone: string | null }
/** A club in DMP's registry with its live numbers for this month. */
export interface RegistryOrg { org: OrgRef; members: number; president: DmpPerson | null; month: { events: number; registrations: number; came: number } }
export interface RosterMember extends DmpPerson { role: OrgRole; joinedAt: Ts; lastCame: Ts | null; quiet: boolean /* no check-in at the club's events for 60 days */ }
/** A memo a club marked sent in the last 7 days (DMP's registry, Oct 13): its events, who said "sent" and when. */
export interface SentMemo { org: OrgRef; sentAt: Ts; by: string | null; events: { id: Id; title: string; startsAt: Ts }[] }
export interface RegistryHit extends DmpPerson { clubs: { org: OrgRef; role: OrgRole }[] }

/** A comment under a post or an event (§4.10): a student (short name, §3) or the club itself. */
export interface Comment { id: Id; person: PersonRef | null; org: OrgRef | null; body: string; at: Ts; mine: boolean; canDelete: boolean;
  replyTo?: { id: Id; name: string; body: string } | null /* the comment it answers, quoted while still up */ }
/** A thread: oldest first; the club's Head+ moderate it and may write as the club (`asOrg`). */
export interface CommentThread { items: Comment[]; on: boolean; canModerate: boolean; asOrg: OrgRef | null }
export type ReportReason = 'spam' | 'insult' | 'danger' | 'other';
/** The admin's queue: one row per reported thing still up. */
/** Something the admin took down from the reports in the last 30 days, still down: Restore undoes it. */
/** The app's team (owner, Oct 22): the owner (admin + founder), admins, moderators; and who is banned (why). */
export interface StaffRow { person: PersonRef; username: string | null; role: PlatformRole; owner: boolean; banReason: string | null; banned?: boolean }
export interface Staff { team: StaffRow[]; banned: StaffRow[]; owner: boolean /* me: may give the admin role, reads the log */ }
export interface AuditRow { id: Id; actor: PersonRef | null; action: string; target: string; targetName: string | null; data: Record<string, unknown>; at: Ts }
export interface TakenDown { target: 'comment' | 'post' | 'event'; id: Id; text: string; at: Ts }
/** The admin panel's numbers: online (10 min), active day/week/month, totals, new today; 30 nightly rows. */
export interface AdminStats { online: number; day: number; week: number; month: number; users: number; students: number; newToday: number;
  days: { day: number; active: number; new: number; students: number }[];
  /** the translator (PLAN 9): Cloudflare's keys set, translated today (UTC), the last error */
  ai?: { on: boolean; today: number; error: string | null };
  today?: number /* opened the app today so far (the visits log) */ }
/** One day of the admin's chart: who opened the app; people null for a day before the visits were kept. */
export interface AdminDay { day: number; active: number; new: number; people: { id: Id; name: string; username: string | null; new: boolean; student: boolean; profile: boolean }[] | null }
/** The AI page in Admin: the translator's state and work. */
export interface AdminAi { on: boolean; today: number; error: string | null; model: string; events: { done: number; waiting: number }; clubs: { done: number; waiting: number };
  failed: { kind: 'event' | 'org'; id: Id; title: string }[] }
/** One of the owner's manual grants ("You gave" on the Awards page). */
export interface GrantItem { id: Id; code: 'bugs' | 'creator_laugh' | 'creator_found'; at: Ts; person: PersonRef }
export interface ReportItem { target: 'comment' | 'post' | 'event' | 'user' | 'photo'; id: Id; text: string; where: { kind: 'post' | 'event' | 'person'; id: Id }; count: number; reasons: Partial<Record<ReportReason, number>>;
  notes: { reason: ReportReason; note: string; at: Ts }[] /* what reporters wrote, newest first, never who */; at: Ts }

/** DMP's view of a leaders meeting: per club, who said yes, who no, who hasn't answered. */
export interface LeadersAnswer { org: OrgRef; people: { person: PersonRef; fullName: string; role: OrgRole; answer: 'yes' | 'no' | 'none' }[] }
/** A club meeting's person for its Head+ (§2b): the answer ("no" with why), whether they came. */
export interface MeetingAnswer { person: PersonRef; fullName: string; role: OrgRole; answer: 'yes' | 'no' | 'none'; note: string | null; came: boolean;
  probation: boolean }

/** "Bring a friend": a friend and where they stand with the event (going only if they show where they go). */
export interface FriendInvite { person: PersonRef; state: 'none' | 'invited' | 'going' }

/** A photo in an event's album: the one who added it or the club's Head+ may take it out. */
export interface AlbumPhoto extends Media { id: Id; canDelete: boolean; by: string | null; mine: boolean } // by: who added it (nick or "First L.")

/** An event's video (server video.py): our own compressed copy, its poster a photo; `error`: too_long | not_a_video. */
export interface Video { id: Id; status: 'uploading' | 'queued' | 'working' | 'ready' | 'failed'; url: string | null; duration: number | null;
  poster: Media | null; error: string | null }

export interface Media {
  id?: Id; url: string; thumb: string; w: number; h: number; blur: string; color?: string | null /* a photo's average colour */;
  focus?: [number, number] | null; // an event cover's point that every frame keeps in view, 0..1; null = the middle
}

/** `logo`: the club's uploaded mark (a thumbnail URL); without one it is its emoji on its cover. */
export interface OrgRef { id: Id; slug: string; name: string; short: string; emoji: string; cover: number; kind: OrgKind; official: boolean; logo?: string | null;
  abbr?: string /* a school's short name, set by api/client.ts from i18n */;
  i18n?: Partial<Record<'ru' | 'kk' | 'en', { name?: string; description?: string; abbr?: string }>> /* applied by api/client.ts */;
  orig?: Record<string, string> /* the fields as typed, before api/client.ts showed a translation */ }

/** A club as the admin sees it (pilot): its leaders by Telegram name, and how many members it has. `student`: signed in
 *  with KBTU — a role counts only then. */
export interface AdminMember { id: Id; role: OrgRole; username: string | null; name: string; student: boolean }
export interface AdminOrg extends OrgRef { team: AdminMember[]; members: number; hidden: boolean }
// a club's event in Admin's delete list, with what deleting it takes along
export interface AdminEvent { id: Id; title: string; status: 'draft' | 'published' | 'cancelled'; startsAt: Ts | null; people: number; came: number; paid: number; photos: number }

export interface Org extends OrgRef {
  description: string;
  links: string[];              // socials: Instagram, TikTok, YouTube, Telegram, a site (lib/social.ts names them)
  subscribers: number;
  members: number;
  upcoming: number;
  recruiting: boolean;          // takes join applications (the club closes it in Studio)
  membersHidden: boolean;       // the club hides its member list from outsiders (owner, Oct 24)
  leaders?: Member[];           // President and Vice, from api.org only
  myRequest: 'pending' | 'rejected' | null; // my application; rejected = declined < 30 days ago, no new one yet
  round?: { id: Id; closesAt: Ts; applied: boolean } | null; // a recruitment round taking applications (casting) and whether I applied
  subscribed: boolean;
  myRole: OrgRole | null;
  myTitle?: string | null;      // the club's own name for my role (§2b)
  myRights?: Right[];           // what I may do in it (§2)
  canBroadcast: boolean;
  canOversee?: boolean;         // DMP: may hold a leaders meeting (§4.10)
}

/** The club's own profile (Vice+, SPEC §2): only what is sent changes. */
/** `logoId`: an upload of mine (uploadPhoto); null takes the logo off. */
export interface OrgPatch { name?: string; short?: string; emoji?: string; cover?: number; description?: string; links?: string[]; recruiting?: boolean; membersHidden?: boolean; logoId?: Id | null; slug?: string } // slug: the President's (A5)

/** A person as other students see them (§3): the nick if they have one, else the short name; their photo (their own or
 *  Telegram's); the founder mark. Organizers get the real name too: lists' `fullName`, the door's `realName`. */
/** Someone in a club as anyone sees them: name and role, never the @username (api.team is the club's own) */
export interface Member { person: PersonRef; role: OrgRole; title: string | null }

export interface PersonRef { id: Id; name: string; nick?: string | null; avatar: string | null; founder: boolean; mark?: 'idea' | null; staff?: 'admin' | 'moderator' | null }  // mark: the idea author's blue seal
/** at the door (Member+): the real short name beside a nick (owner, Oct 5) */
export type DoorRef = PersonRef & { realName: string };

export interface Settings {
  lang: Lang;
  theme: 'light' | 'dark' | null;
  nRemind: boolean;
  nNewEvents: boolean;
  nFriends: boolean;
  showGoing: boolean;
  hideFirstYear: boolean;
}

export interface StudentProfile {
  studentId: string;
  firstName: string;
  lastName: string;
  email: string | null;
  phone: string | null;
  course: number | null;
  school: string | null;
  program: string | null;
  syncedAt: Ts;
  ms: boolean;     // signed in with the KBTU Microsoft account
  consent: string; // the policy version agreed to (lib/legal.ts); 'staff' and 'admin': added by hand
}

/** A club role: the level (what one may do, §2) and the club's own name for it, if it has one (§2b). */
/** A club role's rights (SPEC §2): door (check people in), events, posts (news, replies as the club), people (tags, probation),
 *  team (applications, invites, roles, removing), money (price, Kaspi), profile (the club's page). */
export type Right = 'door' | 'events' | 'posts' | 'people' | 'casting' | 'team' | 'money' | 'memo' | 'profile';
export interface Membership { org: OrgRef; role: OrgRole; title?: string | null; rights?: Right[] }  // rights: in my own memberships

export interface Me {
  id: Id;
  tg: { id: number; username: string | null; firstName: string; lastName: string };
  avatar: string | null;        // what everyone sees: my own photo, or Telegram's
  name: string;                 // what everyone sees: my nick, else the short name (first name + surname initial), or the Telegram name for guests
  nick: string | null;
  photo: { telegram: boolean /* "Photo from Telegram" */; tg: string | null; own: string | null };
  student: StudentProfile | null; // null = guest
  msPending?: { first: string; last: string; email: string } | null; // signed in with Microsoft, the student ID still to type
  relink?: boolean; // typed in before Oct 20 (no Microsoft): signed out until Microsoft confirms that row
  role: PlatformRole;
  canDm: boolean;               // the bot may write (Telegram's "allow messages", or the chat opened)
  founder: boolean;
  mark?: 'idea' | null;
  no: number | null;            // the card number: the order of first KBTU sign-in, the Creator's 0; null for guests
  qr: string | null;            // my badge QR, "<id>_<code>" (§4.4): a random code, so nobody can make up another's; null for guests
  oversee: boolean;             // DMP staff: gets the DMP tab
  bio: string;
  showcase: string[];
  settings: Settings;
  memberships: Membership[];
  counters: { tickets: number; unreadBroadcasts: number; friendRequests: number; reports: number /* admin: open reports */; clubApps: number /* admin: clubs waiting for the check */ };
  /** The badge I show: a club's (an official club I'm in), 'sower' (the creator's own), null: the KBTU one. Owner, Oct 13:
   *  badges as skins; never picked, a new club's comes by itself. */
  skin: Id | 'sower' | null;
  /** "Delete my account" asked: when it goes (a week later); null: not asked, or changed my mind. */
  deleteAt: Ts | null;
  unlocked: { code: string; level: number }[]; // new achievement levels the app hasn't celebrated yet (the unlock moment)
}

export type RegStatus = 'hold' | 'going' | 'waitlist' | 'cancelled';

export interface MyRegistration {
  status: RegStatus;
  cancelReason: 'self' | 'hold_expired' | 'receipt_rejected' | 'removed' | null;
  ticketCode: string | null;
  holdUntil: Ts | null;
  checkedInAt: Ts | null;
  receipt: 'none' | 'accepted' | 'rejected';
  receiptFlags?: string[];      // why my receipt looks wrong, until the organizer looks at it (§4.3): another file may replace it
  free?: boolean;               // one of a paid event's free seats for 1st-year students (§4.3)
  rating?: number | null;       // came: my rating after the event (Me → Recent asks until there is one)
  ics?: string | null;          // going: the signed calendar file's path
  note?: string | null;         // "Can't make it": why (a club meeting asks)
}

export interface EventCard {
  /** the other languages (ai.py), applied by api/client.ts; `orig`: the text as typed */
  i18n?: Partial<Record<'ru' | 'kk' | 'en', { title?: string; description?: string }>>; orig?: Record<string, string>;
  id: Id;
  org: OrgRef;
  status: 'draft' | 'published' | 'cancelled';
  title: string;
  startsAt: Ts;
  endsAt: Ts | null;
  publishedAt?: Ts | null;      // when it went out: News shows a new event of my clubs and follows as a card (Oct 13)
  place: string;
  placeUrl: string | null;      // 2GIS link for off-campus places
  cover: Media | null;          // photo or poster; null → emoji + colour
  video?: Video | null;         // a short vertical video the Feed plays (ready ones only; the editor also sees one being compressed)
  slides: Media[];              // photos after the cover, swiped sideways (PLAN 33)
  emoji: string | null;
  color: string | null;
  tint: string;                 // sheet tint
  seats: number | null;         // null = no limit
  taken: number;                // hold + going
  visibility?: 'public' | 'members' | 'leaders'; // members: the club's team only; leaders: DMP's meeting of club leaders (§4.10)
  leadersFrom?: 'president' | 'vice' | 'head' | null; // a leaders meeting: the lowest role invited
  meeting?: boolean;            // a club meeting (§2b): team-only, the whole club or one tag expected to answer and come
  firstYear: boolean;
  externalUrl: string | null;
  price: number | null;
  regUntil?: Ts | null;         // registration closes; null = open until the start
  freeFirst?: number | null;    // a paid event: how many 1st-year students come free (the first to register)
  freeLeft?: number | null;     // ... of them still free
  my: MyRegistration | null;
  saved: boolean;
  friends: PersonRef[];         // friends going, privacy-filtered; empty for guests
  questions?: number;           // Studio, the club's Head+: students' comments since the club last answered
  toCheck?: number;             // Studio, the club's Head+: receipts that look wrong and nobody looked at yet (§4.3)
  savedBy?: number;             // Studio, the club's Head+: how many saved it ("Save" with a purpose)
  needsVolunteers?: number | null;  // how many volunteers it asks for; null: none
  volunteersAsked?: number;     // Studio, the organizers: applications waiting for an answer
}

export interface EventFull extends EventCard {
  description: string;
  /** volunteers (owner, Oct 15): `mine` my application's state; `asked` (organizers only) how many wait */
  volunteers?: { need: number; senior: boolean; taken: number; mine: 'asked' | 'yes' | 'no' | null; asked?: number } | null;
  chat?: string | null;         // the event's Telegram group (join by request): for those going, volunteers, the team
  chatLinked?: boolean | null;  // the organizers: a group is linked
  meetingTag?: Id | null;       // a meeting for one of the club's tags; null = the whole club
  payToName: string | null;
  payPhone: string | null;
  memo?: MemoAsks | null;       // the club's Head+: what this event asks DMP for in the weekly memo
  badgeName: string | null;
  photos: AlbumPhoto[];          // the guests' album (students only), in the order added
  wideVideo?: Video | null;      // a horizontal muted clip behind the sheet (PLAN 32)
  canAddPhotos: boolean;        // came (checked in) or the team, from the start until a week after the end, room left
  albumOpen?: boolean;          // "Photos from participants": off = only the team adds (absent for non-students)
  updates: EventUpdate[];       // the organizer's updates, newest first (pinned under the title)
  comments: number;             // questions and comments under the event (§4.10)
  commentsOn: boolean;
  discuss: string | null;       // its channel post's comments in Telegram, where the talk goes when there is one (Oct 17)
  myRating: number | null;      // 1..5, my one-tap rating after the event
  canRate: boolean;             // checked in, the event is over, within 7 days
  ratings: RatingSummary | null; // the club's Head+ only: anonymous
}

/** How attendees rated an event (Head+ only, anonymous): average, counts for 1..5, comments without names. */
export interface RatingSummary { avg: number | null; count: number; dist: number[]; comments: { score: number; body: string; at: Ts }[] }

/** An organizer's update on an event (Head+ post it; the bot only says there is one). */
export interface EventUpdate { id: Id; body: string; at: Ts; canDelete: boolean }

/** What the Studio editor sends (create or edit). */
/** Casting (PLAN "Casting"): a club's recruitment round. Departments are the club's tags; up to six questions of its own. */
export type RoundKind = 'short' | 'long' | 'one' | 'many' | 'link';
export interface RoundQuestion { id?: Id; kind: RoundKind; text: string; options?: string[] | null; required: boolean; tagId?: Id | null }
export interface RoundDepartment { tagId: Id; name?: string; color?: string; about: string; places?: number | null }
export interface RoundInput { title: string; picks: number; closesAt: Ts; resultsBy?: Ts | null; declineText?: string;
  departments: RoundDepartment[]; questions: RoundQuestion[] }
export type AppStage = 'new' | 'maybe' | 'next' | 'yes' | 'no';
/** The live round as I see it: a student its form and my application ('sent' until the results, then yes or no); the
 *  casting team its counts by stage too. */
export interface Round { id: Id; title: string; picks: number; closesAt: Ts; resultsBy: Ts | null; open: boolean; status: 'open' | 'closed' | 'done';
  departments: (RoundDepartment & { name: string; color: string })[]; questions: (RoundQuestion & { id: Id })[];
  mine: { departments: Id[]; answers: Record<string, string | string[]>; stage: 'sent' | 'yes' | 'no'; invited: boolean;
    slot: { id: Id; startsAt: Ts; minutes: number; place: string } | null } | null;
  team?: boolean; counts?: Partial<Record<AppStage, number>>; declineText?: string }
/** One application as the casting team sees it: the profile, picks and answers, the team's votes, and what only the app knows. */
export interface RoundApp { id: Id; person: PersonRef; fullName: string; course: number | null; school: string | null; email: string | null; username: string | null;
  departments: Id[]; answers: Record<string, string | string[]>; stage: AppStage; takenTag: Id | null; at: Ts; source: string | null;
  votes: { by: string; mine: boolean; verdict: 'no' | 'maybe' | 'next'; stars: number | null; note: string }[];
  came: number; lastEvent: string | null; friends: number; before: boolean; since: Ts;
  invited: boolean; slot: { id: Id; startsAt: Ts; minutes: number; place: string } | null; showed: boolean | null /* came to the interview */ }
/** An interview time: the team sees who booked it; an invited applicant the ones with room, and theirs (`mine`). */
export interface RoundSlot { id: Id; startsAt: Ts; minutes: number; capacity: number; place: string; left: number; mine?: boolean;
  people?: { appId: Id; person: PersonRef; fullName: string; showed: boolean | null }[] }

/** What a club asks DMP for in its weekly memo (PLAN "Memo in one tap"; the server writes DMP's template from it).
 *  Every request is optional; dates are the form's 'YYYY-MM-DD', times 'HH:MM'. */
export type MemoSide = 'tole' | 'kazybek' | 'abylai' | 'turgut' | 'karimov';  // KBTU's entrances; the last two the dorm's gates
export interface MemoSlot { date?: string; from?: string; to?: string }
export interface MemoAsks {
  /** a KBTU room (the event's place) or the dorm; more date/time slots besides the event's own */
  room?: { any?: boolean; projector?: boolean; board?: boolean; capacity?: number | null; dorm?: boolean; dormPlace?: string; slots?: MemoSlot[] };
  guests?: { side?: MemoSide; list?: string };          // one guest a line: "Name Surname, university or company"
  provide?: { jbl?: boolean; tables?: number | null; chairs?: number | null; mixer?: boolean; cooler?: number | null; other?: string };
  /** dates: several days (often 10-15 weekdays) with one time range; an older `date` reads as [date] */
  promo?: { place?: string; date?: string; dates?: string[]; from?: string; to?: string; extras?: string };
  gear?: { items?: string; outDate?: string; outTime?: string; inDate?: string; inTime?: string; location?: string; side?: MemoSide };
  print?: { items?: { name?: string; count?: number; format?: string; bw?: boolean; note?: string; density?: 0 | 1 | 2 }[] };
  film?: { date?: string; from?: string; to?: string; note?: string };   // the KBTU studio
}
export interface MemoEvent { id: Id; title: string; startsAt: Ts; draft: boolean; sentAt?: Ts; sentBy?: string | null }
/** The week's memo, signed by me (the "memo" right): the text for Outlook (to `to`), the events in it, later ones (in it
 *  with `later`), those already sent, next week's asking for nothing; who opened it last; my signature's parts. */
export interface MemoDraft { to: string; subject: string; text: string; from: Ts; until: Ts; print: { to: string; subject: string; text: string } | null /* the Publishing Center's own letter */;
  guests: boolean; events: MemoEvent[]; later: MemoEvent[]; sent: MemoEvent[]; without: MemoEvent[]; canEdit: boolean;
  opened: { at: Ts; by: string | null } | null;
  sign: { name: string; nameEn: string; kk: string; ru: string; en: string; fixed: boolean };
  signFrom: string /* the signature's first line: items go in before it */ }
export interface MemoSign { nameEn: string; kk: string; ru: string; en: string }

export interface EventInput {
  title: string;
  description: string;
  startsAt: Ts;
  endsAt: Ts | null;
  place: string;
  placeUrl: string | null;
  emoji: string;
  color: string;
  seats: number | null;
  regUntil?: Ts | null;        // registration closes (at most the start); null or left out = open until the start
  firstYear: boolean;
  albumOpen?: boolean;         // "Photos from participants" (who came adds to the album); left out = on
  volunteers?: number | null;  // how many volunteers it needs; null: none
  volunteersSenior?: boolean;  // not year 1
  visibility?: 'public' | 'members' | 'leaders';  // left out: kept as it is; leaders only from an oversight org
  meeting?: boolean;           // a club meeting: only team-only, no seats, no price
  meetingTag?: Id | null;
  leadersFrom?: 'president' | 'vice' | 'head';
  /** A photo from uploadPhoto; null removes the photo; left out keeps whatever the event has. */
  coverId?: Id | null;
  /** A video from uploadVideo, like coverId. */
  videoId?: Id | null;
  /** The sheet's horizontal background clip (uploadVideo with wide). */
  wideVideoId?: Id | null;
  /** Photos after the cover, in order (at most 9); absent keeps them. */
  slideIds?: Id[];
  /** The cover's focus, [x, y] from 0 to 1; null = the middle; left out keeps it. */
  coverFocus?: [number, number] | null;
  /** Paid (§4.3): tenge, null = free; with the name on the Kaspi receipt and the Kaspi phone. Only an official club's
   *  Vice+ send these, and they are fixed once someone has paid; left out keeps them. */
  price?: number | null;
  payToName?: string | null;
  payPhone?: string | null;
  freeFirst?: number | null;
  /** For the weekly memo to DMP; null clears it, left out keeps it. */
  memo?: MemoAsks | null;
}

/** One registration as the organizer sees it (§3: full name for organizers). */
export interface Attendee { person: PersonRef; fullName: string; status: RegStatus; checkedInAt: Ts | null; walkIn: boolean; manual: boolean; at: Ts; free?: boolean; receipt?: AttendeeReceipt | null }
/** A paid event's receipt (§4.3) as the organizer sees it: what OCR read off it (null: not read), `flags` from the
 *  server's checks ('duplicate' the same file or receipt number came before, 'amount_short', 'recipient_mismatch',
 *  'too_early' older than the event, 'unreadable'); `reviewed` once the organizer said it's fine. Flagged ones first. */
export interface AttendeeReceipt {
  id: Id; flags: string[]; reviewed: boolean; at: Ts;
  amount?: number | null; no?: string | null; sender?: string | null; recipient?: string | null; paidAt?: Ts | null;
}
/** The door list for check-in by name (Member+, short names only, §3): going people, the ones still to come first.
 *  `manual` = checked in by hand (no QR). */
export interface DoorPerson { person: DoorRef; checkedInAt: Ts | null; walkIn: boolean; manual: boolean }
/** A walk-in by the full name they typed (A19): full for Head+, short at the door; undo = mine, in the first 10 min */
export interface DoorGuest { id: Id; name: string; at: Ts; linked: boolean; undo: boolean }

/** An application to join, as the club's Vice+ see it (§4.5): enough to write to the person first. */
/** Someone in a club, as its own team sees them (§3: full names and @usernames inside the team). */
export interface TeamMember {
  person: PersonRef; fullName: string; username: string | null; role: OrgRole; joinedAt: Ts;
  quiet?: boolean;              // Vice+: 60 days without a check-in
  roleId?: Id | null; title?: string | null; titleColor?: string | null; // the club's own role (§2b)
  tags?: Id[];                  // the club's tags on them
  dept?: Id | null;             // their department: one of those tags marked department (PLAN 47)
  probation?: boolean; // for the club's Head+ and the person
}

/** Team 2.0 (§2b): the club's own roles (a name on a level), tags, and for Vice+ the open removal requests and bans. */
export type ClubLevel = 'member' | 'head' | 'vice';
export interface ClubRole { id: Id; name: string; color: string; level: ClubLevel; rights: Right[]; count: number; fixed?: boolean /* Vice, Head: official */ }  // level: its highest right's
export interface ClubTag { id: Id; name: string; color: string; count: number; department?: boolean } // department: one per person (PLAN 47)
export interface RemovalRequest { id: Id; person: PersonRef; fullName: string; by: PersonRef | null; ban: boolean; note: string; at: Ts; canDecide: boolean }
export interface ClubBan { person: PersonRef; fullName: string; at: Ts }
export interface TeamSetup { roles: ClubRole[]; tags: ClubTag[]; myDept?: Id | null; removals?: RemovalRequest[]; bans?: ClubBan[] }
/** One person in Team, only what is sent: a level or a club role (Vice+), tags (Head+), probation (on: Head+, off: Vice+). */
export interface MemberPatch { role?: OrgRole; roleId?: Id | null; tags?: Id[]; dept?: Id | null; probation?: boolean }

export interface JoinRequest { id: Id; person: PersonRef; fullName: string; course: number | null; school: string | null; username: string | null; createdAt: Ts }

/** Door scanner answer (§4.4): a ticket or a badge QR. `walkIn` = registered at the door by their badge,
 *  `late` = minutes after the start. */
export type CheckinResult =
  | { result: 'ok' | 'already'; person: DoorRef; at: Ts; came: number; going: number; walkIn: boolean; late: number; flagged?: boolean /* a receipt to look at (§4.3) */ }
  | { result: 'other_event' | 'cancelled' | 'not_found' | 'closed' | 'paid' };

export interface ClassItem { weekday: number; begins: string; ends: string; subject: string; kind: string | null; room: string | null; teacher: string | null;
  names?: Partial<Record<'ru' | 'kk' | 'en', string>> | null /* the subject in each language (signed in since Oct 11) */ }

export interface Post {
  id: Id;
  org: OrgRef;
  audience: 'public' | 'clubs';
  title: string;
  body: string;
  tag: string | null;
  photo: Media | null;
  pinned: boolean;
  featured: boolean;
  commentsOn: boolean;
  comments: number;
  reactions: { fire: number; heart: number };
  mine: { fire: boolean; heart: boolean };
  read: boolean;
  createdAt: Ts;
  canDelete: boolean;           // the club's Head+ (or the admin) may take it down
  canEdit: boolean;             // the club's Head+: edit it, pin it
  editedAt: Ts | null;          // the text, label or photo changed after it went out
  canFeature?: boolean;         // moderators and the admin: a public post on top of List for everyone
}

/** The composer's chips (the UI names them per language). Older posts may carry a free-text tag. */
export type PostTag = 'important' | 'recruiting' | 'results' | 'news';
/** A new post (Head+): `clubs` only for broadcast orgs (DMP, KBTU App); the photo is one of my uploads. */
/** Editing a post (its club's Head+): only what is sent changes; who sees it stays. */
export interface PostPatch { title?: string; body?: string; tag?: PostTag | string | null; photoId?: Id | null; pinned?: boolean }
export interface PostInput { title: string; body: string; tag: PostTag | null; photoId?: Id | null; audience?: 'public' | 'clubs'; pinned?: boolean }

export interface AwardLevel { need: number; reached: boolean; rarity: number }
export interface Achievement {
  code: string;
  emoji: string;
  secret: boolean;
  count: number;
  level: number;                // 0 = not earned; tiers I/II/III/Legend = 1..4
  levels: AwardLevel[];
  rarity: number;               // share of students with level ≥ 1, 0..1
  season?: string;              // season medals: '2026-fall'
  at?: Ts | null;               // when its current level was reached (null: before the dates were kept)
  now?: number;                 // the streak only: weeks in a row up to this one (SPEC §4.11)
}
export interface Badge { eventId: Id; title: string; org: OrgRef; emoji: string; color: string; at: Ts }
export interface Awards { achievements: Achievement[]; badges: Badge[] }

/** Profile card (§4.12) — what the viewer is allowed to see. */
export interface PersonCard extends PersonRef {
  no: number | null;            // the card number (as Me.no)
  course: number | null;
  school: string | null;
  bio: string;
  attended: number;
  clubs: (Omit<Membership, 'role'> & { role: OrgRole | null /* only to the club's own team */ })[];
  past: { org: OrgRef; role: OrgRole | null; since: Ts; until: Ts }[]; // where they were before, by itself (org_history); role as above
  showcase: Achievement[];
  /** The showcase as picked, in order: achievement codes and badges as `b<eventId>` (only earned ones); empty = never
   *  picked, so the badge shows a default (earned achievements, then badges). */
  shelf: string[];
  awards: Awards;
  friendship: 'none' | 'requested' | 'incoming' | 'friends';
  friendsSince: Ts | null;
  going: EventCard[];           // only when friends and they allow it
  skin?: Id | 'sower' | null;   // the badge they show (Me.skin)
  username?: string | null;     // their Telegram @username, only to their own club's team: "Message on Telegram" (owner, Oct 6)
  limited?: boolean;            // a stranger's view (audit M2): no clubs, past roles or event badges
}

/** A friend, or a person in a friend request, on the Friends page. `fullName`: the full one for friends only (§3), the
 *  short one in a request. `at`: friends since, or when the request was made. */
export interface FriendRow { person: PersonRef; fullName: string; course: number | null; school: string | null; at: Ts }
/** The Friends page (§4.7): requests both ways, and the coming events friends go to (only those who let friends see
 *  it; each card's `friends` says who). A quietly declined request of mine stays in `outgoing` for 30 days. */
export interface Friends { friends: FriendRow[]; incoming: FriendRow[]; outgoing: FriendRow[]; going: EventCard[] }
export type Friendship = PersonCard['friendship'];
/** A student found by @username, and where the two of us stand. */
export interface FoundStudent { person: PersonRef; course: number | null; school: string | null; friendship: Friendship; me: boolean }
/** Opening someone's one-time friend link: friends at once, or why not. */
export interface FriendLinkUse { result: 'friends' | 'already' | 'used' | 'self'; person: PersonRef }


/** One application to volunteer, as the organizer sees it: full name and course, like applications to a club. */
export interface VolunteerApp { person: PersonRef; fullName: string; course: number | null; school: string | null; username: string | null;
  note: string; status: 'asked' | 'yes' | 'no'; at: Ts }
