// Awards as the profile shows them (SPEC §4.11): names, tiers, and the hero's data — one place for Me and the
// person sheet.
import type { Achievement, Badge, Id, OrgRef, PersonCard } from './api';
import { t, tn } from './i18n/index.svelte';
import { RANK, roleName, titleOf } from './perms';
import { dayMonth } from './time';
import { data } from './state/data.svelte';
import { nameOf, schoolShort, shortOf } from './short';

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
// an achievement's own drawn coin per metal (Recruiter, owner Nov 2: for now, until better art): bronze, silver, gold, legend
const DRAWN_BY_METAL: Record<string, string[]> = { referral: ['medal_ref_b', 'medal_ref_s', 'medal_ref_g', 'medal_ref_l'] };
/** the picture an achievement shows: its own coin for this level's metal (not earned: the first), else its emoji */
export const artOf = (a: Pick<Achievement, 'code' | 'emoji' | 'level' | 'levels'>): string =>
  DRAWN_BY_METAL[a.code]?.[metalOf(Math.max(1, a.level), a.levels.length)] ?? a.emoji;

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
  const top = [...p.clubs].sort((a, b) => weight(b) - weight(a))[0];
  const close = closest(p.awards.achievements);
  return {
    person: { id: p.id, name: p.name, avatar: p.avatar, founder: false },
    name: p.realName ?? p.name,
    nick: p.realName && p.nick ? p.nick : null,
    status: p.founder ? t('person.founder') : p.mark === 'idea' ? t('person.idea') : null,
    title: p.founder ? 'Creator · KBTU App' : p.mark === 'idea' ? 'Idea author · KBTU App' : top ? (top.role ? `${roleName(top.role, titleOf(top))} · ${shortOf(top.org)}` : nameOf(top.org)) : 'Student',
    line: [p.course ? t('person.course', { n: p.course }) : '', schoolShort(p.school), p.city ?? ''].filter(Boolean).join(' · '),  // city: PLAN 95
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

/** Clubs with a badge of their own (made by hand per official club, PLAN "Club badge"), told by name as on the server
 *  (logic.SKINNED): StudEx; Cheerleading and Knights since Oct 20; Moments and Faces since Oct 29. */
export type Skin = 'studex' | 'cheer' | 'knights' | 'moments' | 'faces';
const SKINS: [Skin, RegExp][] = [['studex', /studex/i], ['cheer', /cheer/i], ['knights', /knight/i], ['moments', /moment/i], ['faces', /faces/i]];
export const skinOf = (o?: OrgRef | null): Skin | null => (o?.official && SKINS.find(([, re]) => re.test(o.name))?.[0]) || null;
export const skinned = (o?: OrgRef | null) => !!skinOf(o);
/** the look a person's badge wears: their pick may be a club they aren't in (anyone may try one on) */
export const lookOf = (p: PersonCard): Look => p.skin === 'sower' ? 'sower'
  : skinOf(p.clubs.find((m) => m.org.id === p.skin)?.org ?? data.orgs.find((o) => o.id === p.skin)) ?? 'kbtu';
/** the word on each one's strap */
export type Look = Skin | 'sower' | 'kbtu';
export const STRAP: Record<Look, string> = { studex: 'STUDEX', cheer: 'CHEER', knights: 'KNIGHTS', moments: 'MOMENTS', faces: 'FACES', sower: 'SOWER', kbtu: 'KBTU' };
/** the looks with their own art (ui/LanyardBand): owner, Oct 20, SOWER keeps its own card; KBTU and StudEx got their
 *  art on Oct 29 */
/** each look's QR: its dark colours (both ≥ 7:1 on the white plate; SOWER plain black) and its mark in the middle
 *  (ui/LookMark; owner, Oct 29: a club's badge had the app's colours and mark) */
export const QR_LOOK: Record<Look, [string, string] | undefined> = { kbtu: QR_TONE, sower: undefined, studex: ['#A9271E', '#0F2350'],
  cheer: ['#2E3258', '#14162E'], knights: ['#1C4C94', '#0D2A63'], moments: ['#7A321F', '#2E1A11'], faces: ['#4B2BC9', '#8E1257'] };
export const banded = (look: Look) => look !== 'sower';
