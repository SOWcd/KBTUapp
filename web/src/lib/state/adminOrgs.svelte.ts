// Admin's organizations: every club, school and office as the admin sees them (hidden ones too), read once as Admin
// opens and shared by its search, its list and an organization's page, so a change on the page shows in the list.
import { api, type AdminOrg, type Id } from '../api';
import { t, tn } from '../i18n/index.svelte';

const KEY = 'adm.recentOrgs';
function read(): Id[] { try { return JSON.parse(localStorage.getItem(KEY) ?? '[]'); } catch { return []; } }

export const adminOrgs = $state<{ list: AdminOrg[] | null; failed: boolean; recent: Id[] }>({ list: null, failed: false, recent: read() });

let rev = 0; // every change made here: a list asked for before it is older than what the store holds
let loading: Promise<void> | null = null;

/** Read again in the background (Admin opening, its list, an organization's page, a decision that changes clubs): one
 *  request at a time; an answer older than a change made meanwhile is dropped and asked for again. A failure with
 *  nothing to show is `failed` (a retry), never an empty list. */
export function loadAdminOrgs(): Promise<void> {
  return (loading ??= (async () => {
    const at = rev;
    let again = false;
    try {
      const l = await api.adminOrgs();
      if (at === rev) { adminOrgs.list = l; adminOrgs.failed = false; } else again = true;
    } catch { if (at === rev) adminOrgs.failed = !adminOrgs.list; }
    loading = null;
    if (again) await loadAdminOrgs();
  })());
}

/** One of them as the server has it now (a role given, hidden, a new club). */
export function putOrg(o: AdminOrg): void {
  rev++;
  const l = adminOrgs.list ?? [];
  adminOrgs.list = l.some((x) => x.id === o.id) ? l.map((x) => (x.id === o.id ? o : x)) : [o, ...l];
}
/** One fact of one of them, into the organization as the store holds it now (never a copy taken before the request). */
export function patchOrg(id: Id, change: (o: AdminOrg) => Partial<AdminOrg>): void {
  rev++;
  adminOrgs.list = adminOrgs.list?.map((x) => (x.id === id ? { ...x, ...change(x) } : x)) ?? null;
}
/** The admin's role is gone: nothing of the list stays. */
export function clearAdminOrgs(): void {
  rev++;
  adminOrgs.list = null; adminOrgs.failed = false;
}

/** The ones opened last come first (owner, Nov 16: running an event with one club, he searched it every time); this device only. */
export function seen(id: Id): void {
  adminOrgs.recent = [id, ...adminOrgs.recent.filter((x) => x !== id)].slice(0, 5);
  try { localStorage.setItem(KEY, JSON.stringify(adminOrgs.recent)); } catch { /* private mode */ }
}
export const byRecent = (a: { id: Id }, b: { id: Id }): number => {
  const at = (id: Id) => { const i = adminOrgs.recent.indexOf(id); return i < 0 ? adminOrgs.recent.length : i; };
  return at(a.id) - at(b.id);
};

/** A row's grey line: how many people, and who leads. */
export function orgLine(o: AdminOrg): string {
  const p = o.team.find((m) => m.role === 'president');
  return [o.members ? tn('adm.members', o.members) : '', p ? (p.username ? '@' + p.username : p.name) : t('adm.noPres')].filter(Boolean).join(' · ');
}
