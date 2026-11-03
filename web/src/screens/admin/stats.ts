// Admin's numbers by day: the server counts days in Almaty time (UTC+5); the nightly rows end yesterday, today is the
// visits log so far (server logic/daily.py).
import type { AdminStats } from '../../lib/api';

/** today's day number in Almaty time */
export const almatyDay = (): number => Math.floor((Date.now() / 1000 + 5 * 3600) / 86400);

/** the last `n` days up to today, each with its count (undefined: no row for it) */
export function week(st: AdminStats, today: number, n = 7): { day: number; n: number | undefined }[] {
  const by = new Map(st.days.map((d) => [d.day, d.active]));
  if (st.today != null) by.set(today, st.today);
  return Array.from({ length: n }, (_, i) => ({ day: today - n + 1 + i, n: by.get(today - n + 1 + i) }));
}
