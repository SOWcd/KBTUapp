// Short names where long ones blow up the layout: a school by its abbreviation everywhere but its own
// page; a club by its own short name (Studio, prefilled with its initials) where it sits inline in a tight line.
import type { OrgRef } from './api';
import { data } from './state/data.svelte';

/** Up to this a club's full name fits a tight line too: "Echo Community" as "EC" looked like a bug */
const FITS = 18;
/** A school's short name always (everyone says SITE); a club's only when its full name is long; the full one until it has one. */
export const shortOf = (o: Pick<OrgRef, 'name' | 'abbr'> & { kind?: OrgRef['kind'] }): string =>
  o.abbr && (o.kind === 'school' || o.name.length > FITS) ? o.abbr : o.name;

/** An org's name in a list or a card: a school by its abbreviation, a club in full. */
export const nameOf = (o: Pick<OrgRef, 'name' | 'abbr' | 'kind'>): string => (o.kind === 'school' ? shortOf(o) : o.name);

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ');
/** A student's or a chat's school as typed (the KBTU portal's full name, or an abbreviation, in any of the three
 *  languages) by its abbreviation in the app's language; one the app doesn't know stays as it is. */
export function schoolShort(s: string | null | undefined): string {
  if (!s) return '';
  const k = norm(s);
  const o = data.orgs.find((x) => x.kind === 'school'
    && [x.name, x.abbr, x.orig?.name, ...Object.values(x.i18n ?? {}).flatMap((tr) => [tr?.name, tr?.abbr])].some((n) => n && norm(n) === k));
  return o ? shortOf(o) : s;
}
