// The timetable as a student lives it (owner, Oct 7: Algorithms 12:00-13:00 and 13:00-14:00 in 388 "is one long class,
// you come to it once"): back-to-back classes of one subject in one room are one, from the first start to the last end;
// a break of up to 10 minutes still joins them. The List draws it as one row with "×2"/"×3" by its hours; the capsule, "I won't go" and
// the event sheet take it as one class.
import type { ClassItem } from './api';
import { at, dayNo, OFFSET, parts } from './time';
import { noClasses } from './academic';

const mins = (hm: string): number => { const [h, m] = hm.split(':').map(Number); return h * 60 + m; };

export function joinClasses(list: ClassItem[]): ClassItem[] {
  const out: ClassItem[] = [];
  for (const c of [...list].sort((a, b) => a.weekday - b.weekday || mins(a.begins) - mins(b.begins))) {
    const prev = out[out.length - 1], gap = prev ? mins(c.begins) - mins(prev.ends) : -1;
    if (prev && prev.weekday === c.weekday && prev.subject === c.subject && prev.room === c.room && gap >= 0 && gap <= 10)
      out[out.length - 1] = { ...prev, ends: c.ends };
    else out.push(c);
  }
  return out;
}

export type Slot = { c: ClassItem; b: number; e: number };
const DAY = 86400;
/** The classes of local day `d` (dayNo) with their start and end as timestamps, in time order. */
export function classesOn(schedule: ClassItem[], d: number): Slot[] {
  const p = parts(d * DAY - OFFSET + 12 * 3600);
  const on = (hm: string) => { const [h, m] = hm.split(':').map(Number); return at(p.y, p.m, p.d, h, m); };
  if (noClasses(`${p.y}-${String(p.m + 1).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`)) return [];
  return schedule.filter((c) => c.weekday === (p.wd || 7)) // 1 = Monday … 7 = Sunday
    .map((c) => ({ c, b: on(c.begins), e: on(c.ends) })).sort((a, b) => a.b - b.b);
}
/** What's left of today: the class on now (if any) first, then the rest. */
export const classesLeft = (schedule: ClassItem[], now: number): Slot[] => classesOn(schedule, dayNo(now)).filter((x) => x.e > now);
