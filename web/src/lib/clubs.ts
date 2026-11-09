// The Clubs tab's orderings: the Student Government first, then the biggest (members, then followers),
// a club nobody's in or follows last; and the search both lists share.
import type { Org, OrgRef } from './api';
import { hit as match, namesOf } from './search';
import { t, tn } from './i18n/index.svelte';
import { dayMonth, nowTs } from './time';

export const weight = (o: Org) => o.members + o.subscribers;
export const byWeight = (a: Org, b: Org) =>
  +!a.gov - +!b.gov || b.members - a.members || b.subscribers - a.subscribers || a.name.localeCompare(b.name);
// any of its names in any language, as the server's search (lib/search.ts)
export const hit = (o: OrgRef, q: string) => match(q, namesOf(o, 'name', 'abbr', 'short'));

/** Whole days until a round closes, 1 at the least. */
export const daysLeft = (closesAt: number) => Math.max(1, Math.ceil((closesAt - nowTs()) / 86400));
/** A round's deadline in words: the days in the last three, else the date. */
export const roundDue = (closesAt: number) => (daysLeft(closesAt) <= 3 ? tn('clubs.daysLeft', daysLeft(closesAt)) : t('clubs.until', { when: dayMonth(closesAt) }));
