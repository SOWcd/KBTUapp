// The Clubs tab's orderings (owner, Oct 25): the Student Government first, then the biggest (members, then followers),
// a club nobody's in or follows last; and the search both lists share.
import type { Org } from './api';

export const weight = (o: Org) => o.members + o.subscribers;
export const byWeight = (a: Org, b: Org) =>
  +!a.gov - +!b.gov || b.members - a.members || b.subscribers - a.subscribers || a.name.localeCompare(b.name);
const norm = (s: string) => s.toLowerCase().replace(/\u0451/g, '\u0435'); // Russian yo → ye, so both spellings match
export const hit = (o: Org, q: string) => [o.name, o.abbr ?? ''].some((x) => norm(x).includes(norm(q.trim())));
