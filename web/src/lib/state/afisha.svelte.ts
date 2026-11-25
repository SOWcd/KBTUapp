// Afisha's optional filters: a school and an event type, over the events already held (no request per tap), kept for
// the session (sessionStorage: a reload keeps them, a new launch starts on everything).
import type { EventCard } from '../api';

/** An event's type, read from what every card carries (there is no type field): its price, online, 1st year, teams. */
export const TYPES = ['free', 'paid', 'online', 'firstYear', 'team'] as const;
export type EventType = (typeof TYPES)[number];
export type Filter = { school: string | null; type: EventType | null };

type Ev = Pick<EventCard, 'price' | 'online' | 'firstYear' | 'teamMin' | 'org' | 'coHost' | 'school'>;

export function isType(e: Ev, k: EventType): boolean {
  switch (k) {
    case 'free': return !e.price;
    case 'paid': return !!e.price;
    case 'online': return e.online;
    case 'firstYear': return e.firstYear;
    case 'team': return e.teamMin != null;
  }
}

/** The schools an event belongs to, by slug: its host or co-host school, or the school it is only for. */
export function schoolsOf(e: Ev): string[] {
  const s = [e.org, e.coHost].filter((o) => o?.kind === 'school').map((o) => o!.slug);
  if (e.school && !s.includes(e.school)) s.push(e.school);
  return s;
}

export const active = (f: Filter): boolean => !!(f.school || f.type);

export function filterEvents<E extends Ev>(events: E[], f: Filter): E[] {
  if (!active(f)) return events;
  return events.filter((e) => (!f.type || isType(e, f.type)) && (!f.school || schoolsOf(e).includes(f.school)));
}

/** The chips worth showing: the types and schools some held event has, in a fixed order (a chip never leads to
 *  nothing), and the chosen ones always (so they can be turned off). */
export function choices(events: Ev[], f: Filter): { types: EventType[]; schools: string[] } {
  const schools = new Set<string>();
  for (const e of events) for (const s of schoolsOf(e)) schools.add(s);
  if (f.school) schools.add(f.school);
  return { types: TYPES.filter((k) => k === f.type || events.some((e) => isType(e, k))), schools: [...schools].sort() };
}

const KEY = 'kbtu.afisha.filter';
function load(): Filter {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) ?? 'null');
    return { school: typeof v?.school === 'string' ? v.school : null, type: TYPES.includes(v?.type) ? v.type : null };
  } catch { return { school: null, type: null }; }
}

export const afishaFilter: Filter = $state(load());

/** A chip's tap: one of each kind at a time; the chosen one again clears it. */
export function pick(kind: 'school', v: string): void;
export function pick(kind: 'type', v: EventType): void;
export function pick(kind: 'school' | 'type', v: string): void {
  (afishaFilter as Record<string, string | null>)[kind] = afishaFilter[kind] === v ? null : v;
  try { sessionStorage.setItem(KEY, JSON.stringify(afishaFilter)); } catch { /* blocked: kept until the app closes */ }
}

export function clearFilter(): void {
  afishaFilter.school = afishaFilter.type = null;
  try { sessionStorage.removeItem(KEY); } catch { /* fine */ }
}
