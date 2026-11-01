// ponytail: throwaway helpers for the Afisha redesign mocks (stage 1, owner approves before building); the chosen
// direction moves its pieces into List.svelte and this folder goes.
import type { EventCard } from '../../../lib/api';
import { t } from '../../../lib/i18n/index.svelte';
import { dayMonth, dayNo, OFFSET, weekday } from '../../../lib/time';

export const dayTs = (d: number) => d * 86400 - OFFSET; // start of local day d
const endOf = (e: EventCard) => e.endsAt ?? e.startsAt + 3 * 3600;

/** what's still ahead, by day: [{ d, events }] */
export function byDay(events: EventCard[], now: number): { d: number; events: EventCard[] }[] {
  const by = new Map<number, EventCard[]>();
  for (const e of events) {
    if (e.status === 'cancelled' || endOf(e) <= now) continue;
    const d = dayNo(e.startsAt);
    if (!by.has(d)) by.set(d, []);
    by.get(d)!.push(e);
  }
  return [...by].sort((a, b) => a[0] - b[0]).map(([d, list]) => ({ d, events: list.sort((a, b) => a.startsAt - b.startsAt) }));
}

/** the events I'm going to in the coming week, soonest first */
export const mine = (events: EventCard[], now: number) =>
  events.filter((e) => e.my?.status === 'going' && e.status !== 'cancelled' && endOf(e) > now && e.startsAt - now < 7 * 86400)
    .sort((a, b) => a.startsAt - b.startsAt);

/** Luma's day header: "Tomorrow" bold, "/ Tuesday" grey; a later day: its weekday, then the date */
export function dayHead(d: number, today: number): [string, string] {
  const w = weekday(dayTs(d) + 12 * 3600);
  const W = w.charAt(0).toUpperCase() + w.slice(1);
  if (d === today) return [t('common.today'), w];
  if (d === today + 1) return [t('common.tomorrow'), w];
  return [W, dayMonth(dayTs(d) + 12 * 3600)];
}
