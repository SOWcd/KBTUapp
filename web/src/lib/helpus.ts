// The one-time "students make this app, want to help?" card on Profile (Me.svelte). Who sees it is decided on the phone
// from the days this phone opened the app: nothing about it goes to the server, no request. Shown on one day only
// (the first day it is due and Profile was looked at), gone for good after a tap or once that day is over.
// ponytail: per phone, counted from the release that brought it; the server's `visits` could decide it per account,
// but that is a new use of that data (the policy first).
const DAYS = 'kb-days', ASKED = 'kb-help-asked', DONE = -1;
const WINDOW = 14, ACTIVE = 5, AGE = 7;

interface Kept { f: number; d: number[] } // the first day seen here; the days of the last WINDOW

/** Opened on ACTIVE different days of the last WINDOW, and here for at least AGE days. */
export const engaged = (k: Kept | null, today: number): boolean =>
  !!k && today - k.f >= AGE && k.d.filter((d) => d > today - WINDOW && d <= today).length >= ACTIVE;

/** The days kept, with today in them. */
export const withDay = (k: Kept | null, today: number): Kept =>
  ({ f: k?.f ?? today, d: [...new Set([...(k?.d ?? []), today])].filter((d) => d > today - WINDOW) });

const read = (): Kept | null => { try { const k = JSON.parse(localStorage.getItem(DAYS) || 'null'); return k && typeof k.f === 'number' && Array.isArray(k.d) ? k : null; } catch { return null; } };
const asked = (): number => { try { return Number(localStorage.getItem(ASKED)) || 0; } catch { return DONE; /* blocked: never ask */ } };
const mark = (v: number) => { try { localStorage.setItem(ASKED, String(v)); } catch { /* blocked */ } };

/** Every launch: today is one of this phone's days (no write once asked for good, or when today is in already). */
export function visit(today: number): void {
  if (asked() === DONE) return;
  const k = read();
  if (k?.d.includes(today)) return;
  try { localStorage.setItem(DAYS, JSON.stringify(withDay(k, today))); } catch { /* blocked: nobody is asked */ }
}
/** Show the card now? */
export const helpDue = (today: number): boolean => { const a = asked(); return (a === 0 || a === today) && engaged(read(), today); };
/** Profile showed it: today is its one day. */
export const helpSeen = (today: number): void => { if (asked() === 0) mark(today); };
/** Tapped: never again. */
export const helpDone = (): void => mark(DONE);
