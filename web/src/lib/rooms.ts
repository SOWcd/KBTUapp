// The map's "free now": a room's classes by the university's timetable (server/tools/rooms.py, /api/map/rooms), read
// in Kazakhstan time whatever the phone's zone. By the timetable only: a room can still be taken.
import { parts } from './time';

/** A room's busy hours by weekday ("1" Monday … "6" Saturday): [9, 10] is 09:00-11:00 */
export type RoomWeek = Record<string, number[]>;
/** free or busy now, and until which hour (null: no more classes today) */
export type RoomNow = { free: boolean; until: number | null };

// ponytail: whole hours, the scrape's grid (a 9:00 class shows busy 9:00-10:00, though the bell rings at 9:50); minutes
// when our own timetable scrape lands
export function roomNow(week: RoomWeek, ts: number): RoomNow {
  const { wd, h } = parts(ts);
  // Sunday and outside 08:00-22:00: everything is free
  const hours = wd === 0 ? [] : (week[String(wd)] ?? []).filter((x) => x >= 8 && x < 22);
  if (hours.includes(h)) {
    let e = h + 1;
    while (hours.includes(e)) e++;
    return { free: false, until: e };
  }
  const next = hours.filter((x) => x > h).sort((a, b) => a - b)[0];
  return { free: true, until: next ?? null };
}
