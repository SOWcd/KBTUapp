// Awards as the profile shows them (SPEC §4.11): names, tiers, and the hero's data — one place for Me and the
// person sheet.
import type { Achievement, Badge, Id, OrgRef, PersonCard } from './api';
import { t, tn } from './i18n/index.svelte';
import { RANK, roleName } from './perms';
import { dayMonth } from './time';
import { data } from './state/data.svelte';
import { nameOf, schoolShort, shortOf } from './short';

export const achName = (a: Achievement): string => (a.secret && !a.level ? t('ach.secret') : t(`ach.${a.code}.name` as 'ach.regular.name'));

export function tierName(a: Achievement): string {
  if (a.level === 0) return a.secret ? t('ach.secret') : t('ach.locked');
  return a.levels.length > 1 ? t(`ach.tier.${a.level}` as 'ach.tier.1') : '';
}

/** The profile QR's ink: KBTU blue into violet, both dark enough for any camera on white. */
export const QR_TONE: [string, string] = ['#1D3CB8', '#5B2BC0'];

export interface ShelfItem { key: string; ach?: Achievement; badge?: Badge; founder?: boolean; idea?: boolean; name: string; sub: string }

export const achItem = (a: Achievement): ShelfItem => ({ key: 'a' + a.code, ach: a, name: achName(a), sub: tierName(a) });
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
  name: string;
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
const tierOf = (i: number) => t(`ach.tier.${i + 1}` as 'ach.tier.1');
/** The closest one to its next level (started ones first, else the nearest goal); secrets don't count. */
/** awards nobody works toward: the creator gives the bug hunter by hand, the first 500 is a one-off */
const GIVEN = ['bugs', 'first50'];
export function closest(ach: Achievement[]): Achievement | undefined {
  const open = ach.filter((a) => !hiddenAch(a) && !GIVEN.includes(a.code) && nextOf(a));
  return [...open].filter((a) => a.count > 0).sort((a, b) => ratio(b) - ratio(a))[0] ?? [...open].sort((a, b) => nextOf(a)!.need - nextOf(b)!.need)[0];
}
export function leftLine(a: Achievement): string {
  const n = nextOf(a)!, left = n.need - a.count;
  return a.levels.length > 1 ? t('awp.left', { n: left, tier: tierOf(a.levels.indexOf(n)) }) : t('awp.leftOne', { n: left });
}

export function hero(p: PersonCard): HeroData {
  const earned = p.awards.achievements.filter((a) => a.level > 0);
  const top = [...p.clubs].sort((a, b) => (b.role ? RANK[b.role] : 0) - (a.role ? RANK[a.role] : 0))[0];  // a role only to the club's own team
  const close = closest(p.awards.achievements);
  return {
    person: { id: p.id, name: p.name, avatar: p.avatar, founder: false },
    name: p.name,
    status: p.founder ? t('person.founder') : p.mark === 'idea' ? t('person.idea') : null,
    title: p.founder ? 'Creator · KBTU App' : p.mark === 'idea' ? 'Idea author · KBTU App' : top ? (top.role ? `${roleName(top.role, top.title)} · ${shortOf(top.org)}` : nameOf(top.org)) : 'Student',
    line: [p.course ? t('person.course', { n: p.course }) : '', schoolShort(p.school), p.city ?? ''].filter(Boolean).join(' · '),  // city: PLAN 95
    bio: p.bio,
    no: p.no == null ? '—' : String(p.no).padStart(5, '0'),
    // the shelf under the badge replaced "0 events · 1 award · 2 clubs" (owner, Oct 14: zeros read as a reproach, the
    // clubs are on the badge already); the events count lives in Awards
    loaded: p.attended >= 0,
    earned: earned.length,
    total: p.awards.achievements.length,
    next: close ? `${achName(close)}: ${leftLine(close).replace(/^./, (c) => c.toLowerCase())}` : null,
    shelf: (p.shelf?.length ? p.shelf.map((k) => shelfItem(p, k)).filter((x): x is ShelfItem => !!x)
      : [...earned.map(achItem), ...p.awards.badges.map(badgeItem)]).slice(0, 6),
  };
}

/** Clubs with a badge of their own (made by hand per official club, PLAN "Club badge"), told by name as on the server
 *  (logic.SKINNED): StudEx; Cheerleading and Knights since Oct 20. */
export type Skin = 'studex' | 'cheer' | 'knights';
const SKINS: [Skin, RegExp][] = [['studex', /studex/i], ['cheer', /cheer/i], ['knights', /knight/i]];
export const skinOf = (o?: OrgRef | null): Skin | null => (o?.official && SKINS.find(([, re]) => re.test(o.name))?.[0]) || null;
export const skinned = (o?: OrgRef | null) => !!skinOf(o);
/** the look a person's badge wears: their pick may be a club they aren't in (anyone may try one on) */
export const lookOf = (p: PersonCard): Look => p.skin === 'sower' ? 'sower'
  : skinOf(p.clubs.find((m) => m.org.id === p.skin)?.org ?? data.orgs.find((o) => o.id === p.skin)) ?? 'kbtu';
/** the word on each one's strap */
export type Look = Skin | 'sower' | 'kbtu';
export const STRAP: Record<Look, string> = { studex: 'STUDEX', cheer: 'CHEER', knights: 'KNIGHTS', sower: 'SOWER', kbtu: 'KBTU' };
/** the looks with their own art (ui/LanyardBand): owner, Oct 20, StudEx, KBTU and SOWER keep their own cards */
export const banded = (look: Look) => look === 'cheer' || look === 'knights';
