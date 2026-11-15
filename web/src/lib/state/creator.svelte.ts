// The creator opens any club's Studio from Admin (owner, Nov 15): the club's President's membership stands in his own
// list while that Studio is open (every Studio screen reads memberships), its routes go as the club's (api staffOrg,
// X-Staff-Org), and "view as" swaps in another role of the club's model, which the server enforces too (X-Staff-Role).
import { api, staffOrg, type Id, type LentStudio, type Membership, type OrgRef } from '../api';
import { RIGHTS } from '../perms';
import { session } from './session.svelte';

type Role = LentStudio['roles'][number];
export const creator = $state<{ org: Id; base: Membership | null; roles: Role[]; role: string }>({ org: 0, base: null, roles: [], role: 'president' });
const picked = new Map<Id, string>(); // "view as" per club, for this session only

/** His membership as the role he views the club as (the President's until the server's answer). */
export function viewAs(): Membership | null {
  const b = creator.base, r = creator.roles.find((x) => x.key === creator.role);
  if (!b || !r) return b;
  return { ...b, role: r.level, title: r.title, titleKk: r.titleKk, titleEn: r.titleEn, rights: r.rights, oversee: b.oversee && r.level !== 'member',
    channel: r.rights.includes('profile') ? b.channel : undefined };
}

/** Admin → a club's Studio: lent at once (the President's rights as the app knows them), the server's copy a beat later. */
export function openAsCreator(org: OrgRef): void {
  creator.org = org.id;
  creator.role = picked.get(org.id) ?? 'president';
  creator.base = { org, role: 'president', rights: RIGHTS.map((x) => x.key).filter((k) => k !== 'reports') };
  creator.roles = [];
  Object.assign(staffOrg, { id: org.id, full: true, role: creator.role, events: new Set<Id>() });
  api.lentStudio(org.id).then((l) => { if (creator.org === org.id) { creator.base = l.membership; creator.roles = l.roles; } }).catch(() => {});
}

export function pickRole(key: string): void {
  creator.role = staffOrg.role = key;
  picked.set(creator.org, key);
}

/** The Studio closed: his own list and requests are his again. */
export function closeCreator(org: Id, real: Membership | undefined): void {
  if (creator.org !== org) return;
  creator.org = 0; creator.base = null; creator.roles = [];
  Object.assign(staffOrg, { id: 0, full: false, role: 'president', events: new Set<Id>() });
  const me = session.me;
  if (me) me.memberships = [...me.memberships.filter((x) => x.org.id !== org), ...(real ? [real] : [])];
}
