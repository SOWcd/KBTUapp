// Admin's organizations: every club, school and office as the admin sees them (hidden ones too), read once as Admin
// opens and shared by its search, its list and an organization's page, so a change on the page shows in the list.
import { api, type AdminOrg, type Id } from '../api';
import { t, tn } from '../i18n/index.svelte';

const KEY = 'adm.recentOrgs';
function read(): Id[] { try { return JSON.parse(localStorage.getItem(KEY) ?? '[]'); } catch { return []; } }

export const adminOrgs = $state<{ list: AdminOrg[] | null; recent: Id[] }>({ list: null, recent: read() });

export function loadAdminOrgs(): void {
  api.adminOrgs().then((l) => (adminOrgs.list = l)).catch(() => (adminOrgs.list ??= []));
}

/** One of them as the server has it now (a role given, hidden, a new club). */
export function putOrg(o: AdminOrg): void {
  const l = adminOrgs.list ?? [];
  adminOrgs.list = l.some((x) => x.id === o.id) ? l.map((x) => (x.id === o.id ? o : x)) : [o, ...l];
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
