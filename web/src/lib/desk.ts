// DMP at a desk: the registry laid out wide on a computer's screen, and opened by itself there at launch.
import type { OrgRef } from './api';

/** From this width the registry is a table with the roster beside it (phones never reach it). */
export const WIDE = '(min-width: 1000px)';

/** The launch opens the registry by itself: an overseer on a computer, on a plain launch (a link of its own wins), and
 *  only while nobody has opened it in this launch yet (opened and closed by hand during a slow start: it stays closed). */
export const deskRegistry = (oversee: boolean | undefined, startParam: string, computer: boolean, opened = false): boolean =>
  computer && !!oversee && !startParam && !opened;

/** The wide registry's chosen club, kept by id: the row's current object (a toggled ✓ replaces it), from the list on
 *  screen only (a search or another month without it: nothing chosen, no roster of a club out of sight). */
export function chosen(id: number | null, rows: { org: OrgRef }[] | null, hits: { clubs: { org: OrgRef }[] }[] | null): OrgRef | null {
  if (id == null) return null;
  const row = rows?.find((o) => o.org.id === id)?.org ?? null;
  if (!hits) return row;
  const hit = hits.flatMap((h) => h.clubs).find((c) => c.org.id === id)?.org;
  return hit ? row ?? hit : null;
}
