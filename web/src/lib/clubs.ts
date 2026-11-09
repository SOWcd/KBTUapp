// The Clubs tab's orderings: the Student Government first, then the biggest (members, then followers),
// a club nobody's in or follows last; and the search both lists share.
import type { EventCard, Org, OrgRef } from './api';
import { hit as match, namesOf } from './search';
import { t, tn } from './i18n/index.svelte';
import { dayMonth, dayMonthShort, nowTs, time, weekdayShort } from './time';

export const weight = (o: Org) => o.members + o.subscribers;
export const byWeight = (a: Org, b: Org) =>
  +!a.gov - +!b.gov || b.members - a.members || b.subscribers - a.subscribers || a.name.localeCompare(b.name);
// any of its names in any language, as the server's search (lib/search.ts)
export const hit = (o: OrgRef, q: string) => match(q, namesOf(o, 'name', 'abbr', 'short'));

/** Whole days until a round closes, 1 at the least. */
export const daysLeft = (closesAt: number) => Math.max(1, Math.ceil((closesAt - nowTs()) / 86400));
/** A round's deadline in words: the days in the last three, else the date. */
export const roundDue = (closesAt: number) => (daysLeft(closesAt) <= 3 ? tn('clubs.daysLeft', daysLeft(closesAt)) : t('clubs.until', { when: dayMonth(closesAt) }));

/** What's next at each club: its soonest event, as one line. */
export function nextByOrg(events: EventCard[]): Map<number, string> {
  const m = new Map<number, string>(), now = nowTs();
  for (const e of [...events].sort((a, b) => a.startsAt - b.startsAt))
    if (e.status !== 'cancelled' && e.startsAt > now && !m.has(e.org.id))
      m.set(e.org.id, `${e.startsAt - now < 6 * 86400 ? weekdayShort(e.startsAt) : dayMonthShort(e.startsAt)} ${time(e.startsAt)} · ${e.title}`);
  return m;
}
/** An initiative at the Ascent's top: its line says it's waiting for DMP. */
export const waitsDmp = (o: Org) => !!o.top && !o.official;
/** A club row's line: waiting for DMP; "recruiting" for one taking applications any time; what's next; its latest event
 *  of the last 30 days; its people. Never a count of followers. */
export function clubSub(o: Org, next: Map<number, string>): string {
  if (waitsDmp(o)) return t('clubs.awaitsDmp');
  const open = o.recruiting && !o.round && !o.myRole ? t('clubs.openNow') : '';
  const now = next.get(o.id) ?? (open ? '' : o.last ? `${weekdayShort(o.last.startsAt)}, ${dayMonthShort(o.last.startsAt)} · ${o.last.title}` : o.members ? tn('club.members', o.members) : '');
  return [open, now].filter(Boolean).join(' · ');
}
