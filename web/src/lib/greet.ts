// The launch toast that greets a student by name (App.svelte greet()). What it says, most useful first: my class
// within the hour or my event today > a holiday or a KBTU date > back after a long absence > the day of the week >
// the time of day. At most once per 3 hours, so it stays a small surprise. Each key is a `|` list (phrase()).
import type { Key } from './i18n/index.svelte';
import type { ClassItem, EventCard } from './api';
import type { Slot } from './classes';
import { dayNo, parts } from './time';

export const EVERY = 3 * 3600; // at most one greeting per this many seconds
const AWAY = 7 * 86400;        // "welcome back" after a week without opening the app

/** What's next for me: a class or an event of mine. */
export interface Next { kind: string; title: string; at: number; emoji: string | null }

/** My next class within the hour, else my event later today: only what's still ahead (a running class isn't news,
 *  the capsule's choice would hide a later one). `slots`: today's classes left, without the ones I'll skip. */
export function nextUp(now: number, slots: Slot[], events: EventCard[], title: (c: ClassItem) => string, emoji: (c: ClassItem) => string): Next | null {
  const c = slots.find((x) => x.b > now && x.b - now <= 3600);
  if (c) return { kind: 'class', title: title(c.c), at: c.b, emoji: emoji(c.c) };
  const e = events.find((e) => e.my?.status === 'going' && e.status !== 'cancelled' && e.startsAt > now && dayNo(e.startsAt) === dayNo(now));
  return e ? { kind: 'event', title: e.title, at: e.startsAt, emoji: e.emoji ?? e.org.emoji ?? null } : null;
}
export interface Hi { key: Key; vars: Record<string, string>; emoji: string }

// ponytail: fixed Gregorian dates; the exam weeks are rough. Add the year's real dates here if the owner wants them exact.
const DAYS: [m: number, from: number, to: number, key: Key, emoji: string][] = [
  [11, 31, 31, 'say.hi.newYear', 'party_popper_3d'], [0, 1, 2, 'say.hi.newYear', 'party_popper_3d'],
  [2, 8, 8, 'say.hi.march8', 'blue_heart_3d'],
  [2, 21, 23, 'say.hi.nauryz', 'sparkles_3d'],
  [8, 1, 1, 'say.hi.sep1', 'books_3d'],
  [11, 16, 16, 'say.hi.independence', 'sparkles_3d'],
  [11, 8, 27, 'say.hi.exams', 'books_3d'], [4, 11, 30, 'say.hi.exams', 'books_3d'],
];

const cut = (s: string, n = 22) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s);

/** The greeting for this launch, or null: greeted less than EVERY ago. `time` formats a timestamp as 18:00. */
export function pickHi(now: number, name: string, next: Next | null, lastOpen: number | null, lastHi: number | null,
  time: (ts: number) => string): Hi | null {
  if (lastHi && now - lastHi < EVERY && now >= lastHi) return null;
  const p = parts(now), h = p.h, vars = { name };
  if (next?.kind === 'class' && next.at > now) {
    return { key: 'say.hi.class', vars: { what: cut(next.title, 26), n: String(Math.ceil((next.at - now) / 60)) }, emoji: next.emoji ?? 'books_3d' };
  }
  if (next?.kind === 'event' && next.at > now) {
    return { key: 'say.hi.event', vars: { what: cut(next.title), time: time(next.at) }, emoji: next.emoji ?? 'party_popper_3d' };
  }
  const day = h >= 6 && DAYS.find(([m, a, b]) => p.m === m && p.d >= a && p.d <= b);
  if (day) return { key: day[3], vars, emoji: day[4] };
  if (lastOpen && now - lastOpen >= AWAY) return { key: 'say.hi.back', vars, emoji: 'blue_heart_3d' };
  if (p.wd === 1 && h >= 6 && h < 12) return { key: 'say.hi.monday', vars, emoji: 'rocket_3d' };
  if (p.wd === 5 && h >= 17) return { key: 'say.hi.friday', vars, emoji: 'party_popper_3d' };
  if ((p.wd === 6 || p.wd === 0) && h >= 9 && h < 22) return { key: 'say.hi.weekend', vars, emoji: 'popcorn_3d' };
  return h < 5 ? { key: 'say.hi.late', vars, emoji: 'crescent_moon_3d' }
    : h < 8 ? { key: 'say.hi.early', vars, emoji: 'hot_beverage_3d' }
    : h < 12 ? { key: 'say.hi.morning', vars, emoji: 'sparkles_3d' }
    : h < 18 ? { key: 'say.hi.day', vars, emoji: 'waving_hand_3d_default' }
    : h < 22 ? { key: 'say.hi.evening', vars, emoji: 'partying_face_3d' }
    : { key: 'say.hi.night', vars, emoji: 'crescent_moon_3d' };
}

const get = (k: string): number | null => { try { return Number(localStorage.getItem(k)) || null; } catch { return null; } };
const put = (k: string, v: number) => { try { localStorage.setItem(k, String(v)); } catch { /* private mode: greet every time */ } };

let prevOpen: number | null | undefined; // the launch before this one, read once per launch

/** Records this launch (every launch, a deep link's too) and keeps the one before it for the absence check. */
export function opened(now: number): void {
  if (prevOpen !== undefined) return;
  prevOpen = get('kb-open');
  put('kb-open', now);
}

/** pickHi with the launch before this one and the last greeting kept on the phone. */
export function hiNow(now: number, name: string, next: Next | null, time: (ts: number) => string): Hi | null {
  opened(now);
  const hi = pickHi(now, name, next, prevOpen ?? null, get('kb-hi'), time);
  if (hi) put('kb-hi', now);
  return hi;
}
