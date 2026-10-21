// Kazakhstan time. The whole country is UTC+5 since March 2024 (no DST). We use a fixed offset
// instead of 'Asia/Almaty': phones with old tz databases still think Almaty is UTC+6 and would
// show every event an hour late. If the law changes again, change OFFSET here and on the server.
import { i18n, t } from './i18n/index.svelte';

export const OFFSET = 5 * 3600;
const DAY = 86400;

/** Seconds since epoch, UTC. */
export const nowTs = (): number => Math.floor(Date.now() / 1000);

/** Local calendar day number (days since epoch in Kazakhstan time). */
export const dayNo = (ts: number): number => Math.floor((ts + OFFSET) / DAY);
/** Start of the local day containing ts, as a UTC timestamp. */
export const dayStart = (ts: number): number => dayNo(ts) * DAY - OFFSET;
/** Local wall-clock parts. */
export function parts(ts: number) {
  const d = new Date((ts + OFFSET) * 1000);
  return { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate(), wd: d.getUTCDay(), h: d.getUTCHours(), min: d.getUTCMinutes() };
}
const p2 = (n: number) => (n < 10 ? '0' : '') + n;
/** Value for <input type="date">: 2026-10-03 in Kazakhstan time. */
export const dateInput = (ts: number): string => { const p = parts(ts); return `${p.y}-${p2(p.m + 1)}-${p2(p.d)}`; };
/** Timestamp from <input type="date"> and <input type="time"> values; NaN when either is incomplete. */
export function fromInputs(date: string, hm: string): number {
  if (!/^\d{4}-\d\d-\d\d$/.test(date) || !/^\d\d:\d\d$/.test(hm)) return NaN;
  const [y, mo, d] = date.split('-').map(Number), [h, mi] = hm.split(':').map(Number);
  return at(y, mo - 1, d, h, mi);
}

/** UTC timestamp for a local date and time. */
export function at(y: number, m: number, d: number, h = 0, min = 0): number {
  return Date.UTC(y, m, d, h, min) / 1000 - OFFSET;
}

const LOCALE = { ru: 'ru-RU', kk: 'kk-KZ', en: 'en-GB' } as const;
const cache = new Map<string, Intl.DateTimeFormat>();
function fmt(opts: Intl.DateTimeFormatOptions, ts: number): string {
  const key = i18n.lang + JSON.stringify(opts);
  let f = cache.get(key);
  if (!f) cache.set(key, (f = new Intl.DateTimeFormat(LOCALE[i18n.lang], { ...opts, timeZone: 'UTC' })));
  // shifted date + UTC formatting = Kazakhstan wall clock, whatever the phone's zone or tz database
  return f.format(new Date((ts + OFFSET) * 1000)).replace(/\.(?=\s|,|$)/g, '');
}

/** 18:00 */
export const time = (ts: number): string => { const p = parts(ts); return p2(p.h) + ':' + p2(p.min); };
/** Short weekday in the UI language (Fri). */
export const weekdayShort = (ts: number): string => fmt({ weekday: 'short' }, ts);
/** Full weekday in the UI language (Friday). */
export const weekday = (ts: number): string => fmt({ weekday: 'long' }, ts);
/** Day and month (3 October). */
export const dayMonth = (ts: number): string => fmt({ day: 'numeric', month: 'long' }, ts);
/** Calendar days 'YYYY-MM-DD' as "12–24 October" or "31 August – 4 September"; one day when from = to. */
export function dayRange(from: string, to: string): string {
  const f = new Intl.DateTimeFormat(LOCALE[i18n.lang], { day: 'numeric', month: 'long', timeZone: 'UTC' }), a = new Date(from + 'T00:00:00Z');
  return from === to ? f.format(a) : f.formatRange(a, new Date(to + 'T00:00:00Z'));
}
/** Day and short month (3 Oct). */
export const dayMonthShort = (ts: number): string => fmt({ day: 'numeric', month: 'short' }, ts);

/** Today · Tomorrow · Fri, 3 Oct */
export function relDay(ts: number, now = nowTs()): string {
  const diff = dayNo(ts) - dayNo(now);
  if (diff === 0) return t('common.today');
  if (diff === 1) return t('common.tomorrow');
  return weekdayShort(ts) + ', ' + dayMonthShort(ts);
}

/** When a post was written: "just now", "5 min ago", "3 h ago" (today), "yesterday", then the date. */
/** "October" (standalone, capitalized) in the app's language. */
/** "Oct 2025": a month of a year, for spans like a role's (person.past) */
export const monthYear = (ts: number): string => fmt({ month: 'short', year: 'numeric' }, ts).replace(/\s*\u0433\.$/, '');
export function monthName(ts: number): string { const m = fmt({ month: 'long' }, ts); return m.charAt(0).toUpperCase() + m.slice(1); }

export function ago(ts: number, now = nowTs()): string {
  const s = now - ts;
  if (s < 60) return t('time.now');
  if (s < 3600) return t('time.min', { n: Math.floor(s / 60) });
  if (dayNo(ts) === dayNo(now)) return t('time.h', { n: Math.floor(s / 3600) });
  if (dayNo(ts) === dayNo(now) - 1) return t('time.yesterday');
  return dayMonth(ts);
}

/** How soon, in words, for a countdown: "now", "in 20 min", "in 3 h" (today), "tomorrow", "Fri, 24 Oct". */
export function soon(ts: number, now = nowTs()): string {
  const s = ts - now;
  if (s <= 0) return t('soon.now');
  if (s < 3600) return t('cap.inMin', { n: Math.ceil(s / 60) });
  if (dayNo(ts) === dayNo(now)) return t('soon.h', { n: Math.round(s / 3600) });
  return relDay(ts, now).toLowerCase();
}

/** "Today · 18:00" — the usual event line. */
export const whenLine = (ts: number, now = nowTs()): string => relDay(ts, now) + ' · ' + time(ts);

/** 10 min · 1 h · 1 h 20 min */
export function duration(seconds: number): string {
  const all = Math.max(0, Math.round(seconds / 60)), h = Math.floor(all / 60), m = all % 60;
  return h === 0 ? t('dur.min', { n: m }) : m === 0 ? t('dur.h', { h }) : t('dur.hm', { h, m });
}

/** 02:14:32 countdown; negative becomes 00:00:00. */
export function countdown(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return p2(Math.floor(s / 3600)) + ':' + p2(Math.floor((s % 3600) / 60)) + ':' + p2(s % 60);
}
