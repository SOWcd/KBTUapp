// Awards as the profile shows them (SPEC §4.11): names, tiers, and the hero's data — one place for Me and the
// person sheet.
import type { Achievement, Badge, Id, OrgRef, PersonCard } from './api';
import { t, tn } from './i18n/index.svelte';
import { RANK, roleName, titleOf } from './perms';
import { dayMonth } from './time';
import { data } from './state/data.svelte';
import { nameOf, schoolShort, shortOf } from './short';
// the clubs' own logos in the middle of their QR (cut by .claude/reports/club-lanyards/make-marks.sh)
import mkCrown from '../assets/lanyards/mk-crown.webp';
import crystal from '../assets/lanyards/crystal.webp';
import speRoundel from '../assets/lanyards/spe-roundel.webp';
import aicheFlask from '../assets/lanyards/aiche-flask.webp';
import bclColor from '../assets/lanyards/bcl-color.webp';
import arthouse from '../assets/lanyards/arthouse.webp';
import qairymColor from '../assets/lanyards/qairym-people-color.webp';
import shadeBrush from '../assets/lanyards/shade-brush-red.webp'; // their red brush on their cream (round 5: the official logo)
import choiceLogo from '../assets/lanyards/choice-logo.webp'; // their Spartan in its gold shield (round 5b)
import jccFlower from '../assets/lanyards/jcc-flower.webp'; // round 5: their sakura, cut from their top layer

/** a badge's variant by name ("Performer"); its meaning ("Performed on stage at ...") */
export const variantName = (badge: string, code: string): string => t(`ach.${badge}.v.${code}` as 'ach.init26.v.init26');
export const variantHow = (badge: string, code: string): string => t(`ach.${badge}.h.${code}` as 'ach.init26.h.init26');
/** the badges with variants, as the server's BADGES (logic/profiles.py), the highest variant first, with their medals */
export const BADGES: { code: string; variants: { code: string; emoji: string }[] }[] = [
  { code: 'init26', variants: [{ code: 'init26p', emoji: 'medal_init26p_2' }, { code: 'init26', emoji: 'medal_init26_2' }, { code: 'init26f', emoji: 'medal_init26f_2' }] },
];
/** what it took: a badge's own variant says what I did there */
/** a badge held in several variants as one entry per held variant, its own medal each; the rest as they are */
export function splitVariants(list: Achievement[]): Achievement[] {
  return list.flatMap((a) => {
    const held = (a.variants ?? []).filter((v) => v.have);
    return held.length > 1 ? held.map((v) => ({ ...a, variant: v.code, emoji: v.emoji, rarity: v.rarity ?? a.rarity })) : [a];
  });
}
export const achKey = (a: Achievement): string => a.code + (a.variant ? ':' + a.variant : '');
export const achHow = (a: Achievement): string => (a.variant ? variantHow(a.code, a.variant) : t(`ach.${a.code}.how` as 'ach.regular.how'));
export const achName = (a: Achievement): string => (a.secret && !a.level ? t('ach.secret') : t(`ach.${a.code}.name` as 'ach.regular.name'));

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];
/** a level (from 1) of `of` by name: Roman numerals, the last of four or more is Legend (the bot's texts.tier_name) */
export const tierLabel = (level: number, of: number): string => (level === of && of >= 4 ? t('ach.tier.legend') : ROMAN[level - 1]);
/** a level's metal, 0 bronze, 1 silver, 2 gold, 3 legend: four levels one each; nine (Recruiter) share them out,
 *  I-III bronze, IV-VI silver, VII-VIII gold */
export const metalOf = (level: number, of: number): number => (of <= 4 ? level - 1 : level === of ? 3 : Math.floor(((level - 1) * 3) / (of - 1)));
export const METALS = ['bronze', 'silver', 'gold', 'legend'];
// achievements drawn in layers (public/medals, made by tools/medals.mjs; owner, Nov 3: crisp at any size, the art
// floating under a still rim with the tilt): Recruiter per level (a constellation, one more friend lit each level, the
// rim the level's metal), the anthem's colonnade at sunrise under its staff
const LAYERED: Record<string, string> = { referral: 'layer_rc', anthem: 'layer_an' };
/** the picture an achievement shows: its own medal for this level (not earned: the first), else its emoji */
export const artOf = (a: Pick<Achievement, 'code' | 'emoji' | 'level' | 'levels'>): string =>
  a.code in LAYERED ? LAYERED[a.code] + (a.levels.length > 1 ? Math.max(1, a.level) : '') : a.emoji;
/** a layered medal's files back to front, each with its depth (+ near, against the tilt; - far; 0 the still rim) */
export function layersOf(art: string): [string, number][] | null {
  const rc = /^layer_rc(\d)$/.exec(art);
  if (rc) { const m = 'bsgl'[metalOf(+rc[1], 9)]; return [[`rc-field-${m}`, -1], [`rc-net-${rc[1]}`, 0.5], [`rc-core-${m}`, 1], [`rc-rim-${m}`, 0]]; }
  return art === 'layer_an' ? [['an-field', -1], ['an-staff', 0.5], ['an-hall', 1], ['an-rim', 0]] : null;
}

export function tierName(a: Achievement): string {
  if (a.level === 0) return a.secret ? t('ach.secret') : t('ach.locked');
  return a.levels.length > 1 ? tierLabel(a.level, a.levels.length) : '';
}

/** The profile QR's ink: KBTU blue into violet, both dark enough for any camera on white. */
export const QR_TONE: [string, string] = ['#1D3CB8', '#5B2BC0'];

export interface ShelfItem { key: string; ach?: Achievement; badge?: Badge; founder?: boolean; idea?: boolean; name: string; sub: string }

export const achItem = (a: Achievement): ShelfItem => ({ key: 'a' + achKey(a), ach: a, name: achName(a), sub: tierName(a) });
export const badgeItem = (b: Badge): ShelfItem => ({ key: 'b' + b.eventId, badge: b, name: b.title, sub: dayMonth(b.at) });
/** the Creator's seal by the name, up close: what it is and why */
export const founderItem = (): ShelfItem => ({ key: 'founder', founder: true, name: t('person.founder'), sub: '' });
/** the idea author's blue seal */
export const ideaItem = (): ShelfItem => ({ key: 'idea', idea: true, name: t('person.idea'), sub: '' });
/** A showcase key (an achievement code, or b<event id> for a badge) as an item of this person's, if they have it. */
export function shelfItem(p: PersonCard, key: string): ShelfItem | null {
  const b = /^b\d+$/.test(key) ? p.awards.badges.find((x) => 'b' + x.eventId === key) : undefined;
  if (b) return badgeItem(b);
  const a = p.awards.achievements.find((x) => x.code === key && x.level > 0);
  return a ? achItem(a) : null;
}

export interface HeroData {
  person: { id: Id; name: string; avatar: string | null; founder: boolean };
  frame: string | null;    // drawn over the photo (ui/Frame)
  name: string;           // the real short name (a nick never hides it on the lanyard, owner Nov 2)
  nick: string | null;     // under it
  status: string | null;   // the one mark by the name (Creator for now; DMP comes with the status field)
  title: string;           // the lanyard line: the status, else the top club title, else "Student"
  line: string;            // course · school · city
  bio: string;
  no: string;              // the card number, zero-padded: the order of first KBTU sign-in; the Creator's is 00000
  loaded: boolean;         // a card the app only partly knows yet (attended < 0): no counts rather than wrong zeros
  earned: number;          // achievements reached, of `total`
  total: number;
  next: string | null;     // the closest one to its next level, as a line: the reason to go to one more event
  shelf: ShelfItem[];      // the showcase: up to 6 achievements and badges
}

export const nextOf = (a: Achievement) => a.levels.find((l) => !l.reached);
const hiddenAch = (a: Achievement) => a.secret && a.level === 0;
const ratio = (a: Achievement) => { const n = nextOf(a); return n ? a.count / n.need : 1; };
/** The closest one to its next level (started ones first, else the nearest goal); secrets don't count. */
/** one-off medals for an event (not levels): Awards shows them among the badges */
export const MEDALS = ['first50', 'init26'];
/** awards nobody works toward: the creator gives the bug hunter by hand, the medals are one-offs */
const GIVEN = ['bugs', ...MEDALS];
export function closest(ach: Achievement[]): Achievement | undefined {
  const open = ach.filter((a) => !hiddenAch(a) && !GIVEN.includes(a.code) && nextOf(a));
  return [...open].filter((a) => a.count > 0).sort((a, b) => ratio(b) - ratio(a))[0] ?? [...open].sort((a, b) => nextOf(a)!.need - nextOf(b)!.need)[0];
}
export function leftLine(a: Achievement): string {
  const n = nextOf(a)!, left = n.need - a.count;
  return a.levels.length > 1 ? t('awp.left', { n: left, tier: tierLabel(a.levels.indexOf(n) + 1, a.levels.length) }) : t('awp.leftOne', { n: left });
}

export function hero(p: PersonCard): HeroData {
  const earned = p.awards.achievements.filter((a) => a.level > 0);
  // the lanyard's line: the most important team first, DMP, then the Student Government, then clubs; within one tier the
  // higher role (owner, Oct 31: a minister read "Head of Events · Choice"). A role only to the club's own team
  const weight = (c: PersonCard['clubs'][number]) => (c.role ? 100 : 0) + (c.org.kind === 'office' ? 20 : c.org.gov ? 10 : 0) + (c.role ? RANK[c.role] : 0);
  // ...unless I wear one of my clubs' lanyards: then its line is that club's (Nov 3: a student wanted his other club's
  // role on the card and found no setting; the lanyard I pick is the setting)
  const top = p.clubs.find((c) => c.org.id === p.skin) ?? [...p.clubs].sort((a, b) => weight(b) - weight(a))[0];
  const close = closest(p.awards.achievements);
  return {
    person: { id: p.id, name: p.name, avatar: p.avatar, founder: false },
    frame: p.frame ?? null,
    name: p.realName ?? p.name,
    nick: p.realName && p.nick ? p.nick : null,
    status: p.founder ? t('person.founder') : p.mark === 'idea' ? t('person.idea') : null,
    title: p.founder ? 'Creator · KBTU App' : p.mark === 'idea' ? 'Idea author · KBTU App' : top ? (top.role ? `${roleName(top.role, titleOf(top))} · ${CLUBS[top.org.slug]?.short ?? shortOf(top.org)}` : CLUBS[top.org.slug]?.short ?? nameOf(top.org)) : 'Student',
    line: [p.course ? t(p.master ? 'person.courseM' : 'person.course', { n: p.course }) : '', schoolShort(p.school), p.city ?? ''].filter(Boolean).join(' · '),  // city: PLAN 95
    bio: p.bio,
    no: p.no == null ? '—' : String(p.no).padStart(5, '0'),
    // the shelf under the badge replaced "0 events · 1 award · 2 clubs" (owner, Oct 14: zeros read as a reproach, the
    // clubs are on the badge already); the events count lives in Awards
    loaded: p.attended >= 0,
    earned: earned.length,
    total: p.awards.achievements.length,
    next: close ? `${achName(close)}: ${leftLine(close).replace(/^./, (c) => c.toLowerCase())}` : null,
    // the picked ones first, then the rest in their free places: a new award shows at once (owner, Nov 1)
    shelf: [...new Map([...(p.shelf ?? []).map((k) => shelfItem(p, k)), ...earned.map(achItem), ...p.awards.badges.map(badgeItem)]
      .filter((x): x is ShelfItem => !!x).map((x) => [x.key, x])).values()].slice(0, 6),
  };
}

/** Clubs with a lanyard of their own, by slug (any club, official or not: owner, Nov 2), as the server's
 *  logic.LANYARDS (tests/test_lanyards.py holds the two equal). The first five are drawn by hand (ui/LanyardBand), each
 *  under its own look's name; the rest are CLUB_LOOKS, one template filled with the club's colours and mark. */
const SKINS = { studex: 'studex', kbtucheerleadingclub: 'cheer', kbtuknights: 'knights', moments: 'moments', faceskbtu: 'faces' } as const;
export type Hand = (typeof SKINS)[keyof typeof SKINS];

/** One club's lanyard: its scene is its own (ui/ClubScene); the frame round it is this table, as CSS variables
 *  (lookVars) for the card under the scene, the strap, the strip, the photo's ring, the text and the QR: their colours are
 *  data here, not CSS per club. */
export interface ClubLook {
  strap: string;                    // the strap's word, read up the strap: one line of up to ~8 letters, or two (a \n); three or fewer set big and bold
  strip: string;                    // the word on the strip at the card's foot
  bg: [string, string, string];     // the card under its scene, and the badge's body below its band (MyQr): top, middle, foot
  straps: [string, string, string]; // the strap: its edges, its middle, its letters
  holo: [string, string, string];   // the strip: two stops and its letters
  role: string;                     // the role line
  qr: [string, string];             // the QR's ink, both >= 7:1 on white (awards.test.ts)
  plate: [string, string];          // the QR's middle under the club's logo
  mark: string;                     // the club's logo in the QR's middle
  ring?: string;                    // the photo's ring (white)
  ink?: [string, string];           // the name and the meta line on a light card (white on the dark ones)
  short?: string;                   // the club's own short name in the role line, over the app's (JCC asked, round 5)
}
export const CLUB_LOOKS = {
  mountainkingskbtu: { strap: 'MOUNTAIN\nKINGS', strip: 'MOUNTAIN KINGS', bg: ['#0B1660', '#1F47C2', '#060B30'],
    straps: ['#13248A', '#3A6BEA', '#FFFFFF'], holo: ['#E4ECFA', '#AFC2E6', '#0B1660'], role: '#BCD2FF', qr: ['#12308F', '#0A1A5E'], plate: ['#2A5BE0', '#0B1660'], mark: mkCrown },
  crystalkbtu: { strap: 'CRYSTAL', strip: 'CRYSTAL', bg: ['#0E4652', '#0C3A46', '#05222B'],
    straps: ['#0B3A45', '#2B7F8F', '#C6FBFF'], holo: ['#E8FDFF', '#A3DEE8', '#0B3A45'], role: '#9EF1FF', qr: ['#0C5260', '#062C36'], plate: ['#2B7F8F', '#0B3A45'], mark: crystal },
  spekbtu: { strap: 'SPE', strip: 'SPE', bg: ['#16427A', '#0B1E40', '#040B1C'],
    straps: ['#0B2A55', '#2D5C94', '#D4E3F2'], holo: ['#D4E3F2', '#9AB7D6', '#0B2A55'], role: '#B4CDE6', qr: ['#0D2D5A', '#1A467E'], plate: ['#FFFFFF', '#FFFFFF'], mark: speRoundel },
  aichekbtu: { strap: 'AICHE', strip: 'AICHE', bg: ['#1767B2', '#0A4A85', '#052A52'],
    straps: ['#0A4A85', '#2A7BC8', '#FFFFFF'], holo: ['#FFFFFF', '#DCE9F5', '#0A4A85'], role: '#C2E0FF', qr: ['#0A4A85', '#062F5A'], plate: ['#2A7BC8', '#0A4A85'], mark: aicheFlask },
  bigcitylightskbtu: { strap: 'BIG CITY\nLIGHTS', strip: 'BIG CITY LIGHTS', bg: ['#260A46', '#1A0A33', '#0B0418'],
    straps: ['#8C33C9', '#E8457A', '#FFFFFF'], holo: ['#FFFFFF', '#F1E4FF', '#6A22B8'], role: '#FFB8E0', qr: ['#9A1F52', '#4E1CA0'], plate: ['#FFFFFF', '#FFFFFF'], mark: bclColor },
  arthousekbtu: { strap: 'ARTHOUSE', strip: 'ARTHOUSE', bg: ['#3A0A16', '#12030A', '#120408'],
    straps: ['#4A1424', '#8A2E45', '#F6E3C8'], holo: ['#F6E3C8', '#D9B27C', '#3A0F1E'], role: '#FFD29A', qr: ['#6B1A2E', '#3A0F1E'], plate: ['#8A2E45', '#3A0F1E'], mark: arthouse },
  qairymdylyqkbtu: { strap: 'QAIRYMDYLYQ', strip: 'QAIRYMDYLYQ', bg: ['#46103A', '#4A0F2C', '#2A0818'],
    straps: ['#C2412A', '#F08A3A', '#FFFFFF'], holo: ['#FFF4DC', '#FFD27A', '#8E1F4F'], role: '#FFE3A3', qr: ['#A3203F', '#6B1640'], plate: ['#FFFFFF', '#FFFFFF'], mark: qairymColor },
  shadekbtu: { strap: 'SHADE', strip: 'SHADE', bg: ['#F6EEE2', '#EDE0CC', '#E4D4BC'],
    straps: ['#A60000', '#D3110F', '#F6EEE2'], holo: ['#C80000', '#9E0000', '#F6EEE2'], role: '#B00000', qr: ['#B00000', '#5E0000'], plate: ['#FBF6EE', '#EEE3D2'],
    mark: shadeBrush, ring: '#FFFFFF', ink: ['#1F1612', 'rgba(31, 22, 18, 0.68)'] },
  // Japanese Culture (Nov 2, from their own layers): sakura on pink, their shanyrak; their motto on the strip as they
  // asked it, the strap and the role line just JCC (round 5)
  japanesecultureclub: { strap: 'JCC', short: 'JCC', strip: 'JCC \u00b7 \u0411\u0456\u0440 \u0448\u0430\u04a3\u044b\u0440\u0430\u049b!',
    bg: ['#E3B0C2', '#DCA2B8', '#C98AA3'], straps: ['#4A1F3A', '#7A3460', '#FFE3EC'], holo: ['#5A2448', '#3E1530', '#FFE3EC'], role: '#7A1F4A',
    qr: ['#6B1F45', '#3E1530'], plate: ['#FFFFFF', '#F6E9EE'], mark: jccFlower, ink: ['#2A0F20', 'rgba(42, 15, 32, 0.7)'] },
  // Choice (ambassadors; round 5b, their official logo): their near-black navy, the shield's gold, the helmet's white
  choice: { strap: 'CHOICE', strip: 'CHOICE', bg: ['#1E2340', '#141623', '#0A0B14'], straps: ['#0E1020', '#262B4A', '#E2BC72'],
    holo: ['#F2D9A0', '#C79A48', '#141623'], role: '#E2BC72', qr: ['#141623', '#4A3610'], plate: ['#141623', '#0A0B14'], mark: choiceLogo },
} satisfies Record<string, ClubLook>;
// the schools' (Nov 2: official shields and colours allowed), each its own students' alone (server: logic.SCHOOL_LANYARDS,
// by students.school); the scene is ui/SchoolScene, the shield cut by .claude/reports/school-lanyards/make-shields.sh
const SHIELDS = import.meta.glob('../assets/lanyards/school-*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
const shield = (slug: string) => SHIELDS[`../assets/lanyards/school-${slug}.webp`];
export const SCHOOL_LOOKS = {
  site: { strap: 'SITE', strip: 'SITE', bg: ['#0A64A0', '#085B94', '#04325A'], straps: ['#064A7A', '#0A6FB5', '#F5C242'], holo: ['#F5C242', '#E2A92A', '#04325A'], role: '#FFD872', qr: ['#07507F', '#04325A'], plate: ['#085B94', '#04325A'], mark: shield('site') },
  seogi: { strap: 'SEPI', strip: 'SEPI', bg: ['#302E26', '#1E1D18', '#100F0C'], straps: ['#C9B848', '#E6D464', '#1A1A18'], holo: ['#E6D464', '#CDB94A', '#1A1A18'], role: '#F2E27A', qr: ['#3A3410', '#1A1A18'], plate: ['#1E1D18', '#100F0C'], mark: shield('seogi') },
  geology: { strap: 'GEOLOGY', strip: 'GEOLOGY', bg: ['#54705A', '#48644B', '#2E4232'], straps: ['#3A5240', '#5C7E60', '#E9DDB4'], holo: ['#E9DDB4', '#CDBB86', '#2E4232'], role: '#E9DDB4', qr: ['#2E4232', '#1C2A20'], plate: ['#48644B', '#2E4232'], mark: shield('geology') },
  business: { strap: 'BS', strip: 'BS', bg: ['#2C3E68', '#233253', '#121A2E'], straps: ['#1A2642', '#34497A', '#E7C873'], holo: ['#F3E2B0', '#D7B868', '#233253'], role: '#E7C873', qr: ['#233253', '#121A2E'], plate: ['#233253', '#121A2E'], mark: shield('business') },
  ise: { strap: 'ISE', strip: 'ISE', bg: ['#E81E12', '#C80E06', '#780602'], straps: ['#A80B05', '#E8241A', '#FFFFFF'], holo: ['#FFFFFF', '#F3DAD8', '#B00B04'], role: '#FFE1DD', qr: ['#A00A04', '#600402'], plate: ['#C80E06', '#780602'], mark: shield('ise') },
  kma: { strap: 'KMA', strip: 'KMA', bg: ['#1C2048', '#151837', '#0A0C1E'], straps: ['#0E1030', '#2A2F6A', '#FFFFFF'], holo: ['#FFFFFF', '#DCE0F2', '#151837'], role: '#C9D0FF', qr: ['#151837', '#2A2F6A'], plate: ['#151837', '#0A0C1E'], mark: shield('kma') },
  law: { strap: 'LAW', strip: 'LAW', bg: ['#385C80', '#2D4E6D', '#182C40'], straps: ['#1F3A54', '#3E6890', '#FFFFFF'], holo: ['#E6EEF7', '#B8CADC', '#2D4E6D'], role: '#CFE0F2', qr: ['#2D4E6D', '#182C40'], plate: ['#2D4E6D', '#182C40'], mark: shield('law') },
  sam: { strap: 'SAM', strip: 'SAM', bg: ['#406484', '#355470', '#1E3042'], straps: ['#243C52', '#4A7092', '#FFFFFF'], holo: ['#E6F0FA', '#B6CCE0', '#355470'], role: '#CFE6FF', qr: ['#355470', '#1E3042'], plate: ['#355470', '#1E3042'], mark: shield('sam') },
  sce: { strap: 'SCE', strip: 'SCE', bg: ['#6E549E', '#5D4488', '#342450'], straps: ['#46306C', '#7A5CB0', '#FFFFFF'], holo: ['#EFE9FA', '#CBBDEB', '#5D4488'], role: '#E2D6FF', qr: ['#5D4488', '#342450'], plate: ['#5D4488', '#342450'], mark: shield('sce') },
  smsgt: { strap: 'SMSGT', strip: 'SMSGT', bg: ['#107A50', '#0B6542', '#053824'], straps: ['#08523A', '#14905E', '#FFFFFF'], holo: ['#E4F5EC', '#B4DEC6', '#0B6542'], role: '#BDF2D3', qr: ['#0B6542', '#053824'], plate: ['#0B6542', '#053824'], mark: shield('smsgt') },
  sss: { strap: 'SSS', strip: 'SSS', bg: ['#386052', '#2C4D42', '#182C26'], straps: ['#203A32', '#3E6A5A', '#FFFFFF'], holo: ['#E6F2EC', '#B9D6C8', '#2C4D42'], role: '#CDEBDD', qr: ['#2C4D42', '#182C26'], plate: ['#2C4D42', '#182C26'], mark: shield('sss') },
} satisfies Record<string, ClubLook>;
export type ClubSlug = keyof typeof CLUB_LOOKS | keyof typeof SCHOOL_LOOKS;
const CLUBS: Record<string, ClubLook> = { ...CLUB_LOOKS, ...SCHOOL_LOOKS };
/** a school's lanyard (ui/SchoolScene), not a club's */
export const isSchool = (look: Look) => look in SCHOOL_LOOKS;
export const clubLook = (look: Look): ClubLook | undefined => CLUBS[look];

export type Skin = Hand | ClubSlug;
export const skinOf = (o?: OrgRef | null): Skin | null => (o && (o.kind === 'school' ? (o.slug in SCHOOL_LOOKS ? (o.slug as ClubSlug) : null)
  : (SKINS as Record<string, Hand>)[o.slug] ?? (o.slug in CLUB_LOOKS ? (o.slug as ClubSlug) : null))) || null;
export const skinned = (o?: OrgRef | null) => !!skinOf(o);
/** the look a person's badge wears: their pick may be a club they aren't in (anyone may try one on) */
export const lookOf = (p: PersonCard): Look => p.skin === 'sower' ? 'sower'
  : skinOf(p.clubs.find((m) => m.org.id === p.skin)?.org ?? data.orgs.find((o) => o.id === p.skin)) ?? 'kbtu';
/** the org a look belongs to, as this person's card knows it (their clubs first, then the app's list): its logo is the
 *  card's medallion (ui/OrgMedal) */
export const orgOfLook = (p: PersonCard, look: Look): OrgRef | undefined =>
  look === 'kbtu' || look === 'sower' ? undefined : p.clubs.find((m) => skinOf(m.org) === look)?.org ?? data.orgs.find((o) => skinOf(o) === look);
/** the word on each one's strap */
export type Look = Skin | 'sower' | 'kbtu';
const clubWords = Object.fromEntries(Object.entries(CLUBS).map(([k, c]) => [k, c.strap])) as Record<ClubSlug, string>;
export const STRAP: Record<Look, string> = { studex: 'STUDEX', cheer: 'CHEER', knights: 'KNIGHTS', moments: 'MOMENTS', faces: 'FACES', sower: 'SOWER', kbtu: 'KBTU', ...clubWords };
/** the looks with their own art (ui/LanyardBand): owner, Oct 20, SOWER keeps its own card; KBTU and StudEx got their
 *  art on Oct 29 */
/** each look's QR: its dark colours (both ≥ 7:1 on the white plate; SOWER plain black) and its mark in the middle
 *  (ui/LookMark; owner, Oct 29: a club's badge had the app's colours and mark) */
export const QR_LOOK: Record<Look, [string, string] | undefined> = { kbtu: QR_TONE, sower: undefined, studex: ['#A9271E', '#0F2350'],
  cheer: ['#2E3258', '#14162E'], knights: ['#1C4C94', '#0D2A63'], moments: ['#7A321F', '#2E1A11'], faces: ['#4B2BC9', '#8E1257'],
  ...(Object.fromEntries(Object.entries(CLUBS).map(([k, c]) => [k, c.qr])) as Record<ClubSlug, [string, string]>) };
/** a template look's colours as CSS variables, on the element its card, strap, strip and QR mark sit in ('' for the
 *  hand-drawn ones) */
export function lookVars(look: Look): string {
  const c: ClubLook | undefined = CLUBS[look];
  if (!c) return '';
  const lines = c.strap.split('\n'), long = Math.max(...lines.map((l) => l.length));
  return [['c1', c.bg[0]], ['c2', c.bg[1]], ['c3', c.bg[2]], ['s1', c.straps[0]], ['s2', c.straps[1]], ['s3', c.straps[2]],
    ['h1', c.holo[0]], ['h2', c.holo[1]], ['h3', c.holo[2]], ['role', c.role], ['ring', c.ring ?? 'white'], ['p1', c.plate[0]], ['p2', c.plate[1]],
    // the strap: two lines set tight (as their own mock does), a long word a size smaller, else as the others
    ['sf', lines.length > 1 ? '5.6px' : long > 9 ? '5.2px' : long > 7 ? '6.5px' : long <= 3 ? '11px' : '7.5px'], ['sfw', long <= 3 ? '900' : '800'], ['sl', lines.length > 1 || long > 7 ? '0.06em' : long <= 3 ? '0.02em' : '0.12em'],
    ['slh', lines.length > 1 ? '7.5px' : '26px'],
    ['ink', c.ink?.[0] ?? 'white'], ['ink2', c.ink?.[1] ?? 'rgba(255, 255, 255, 0.8)'], ['tsh', c.ink ? 'none' : '0 1px 2px rgba(0, 0, 0, 0.3)'], ['hs', c.ink ? '0.2' : '0.45']]
    .map(([k, v]) => `--${k}: ${v}`).join('; ');
}
export const banded = (look: Look) => look !== 'sower';
/** The creator's card, seal and strip (round 5b, owner: "redo everything"): two concepts, one line to switch.
 *  'holo': black titanium, a guilloche rosette in holographic foil round the seal, the seal's rim iridescent;
 *  'gold': black lacquer and gold leaf, the seal a gold coin. */
export const SOWER: 'holo' | 'gold' = 'gold'; // owner, Nov 3: the gold one
