// Whether what the staff asked for may still be written (review Nov 17): a role taken away while an answer is on its
// way (a role change, the organizations, the numbers, the inbox) must not put privileged data back into the stores.
// One epoch for every staff request: it moves each time my role steps down, and the stores that hold staff data
// clear themselves then (onStaffLoss), whether or not an Admin page is open.
import { session } from './session.svelte';

type Need = 'admin' | 'staff';
const rank = (): number => (session.me?.role === 'admin' ? 2 : session.me?.role === 'moderator' ? 1 : 0);
const needs = (need: Need): number => (need === 'admin' ? 2 : 1);

let epoch = 0, was = 0, watching = false; // nothing here reads the session as the module loads (it may not be set up yet)
const lost: ((has: (need: Need) => boolean) => void)[] = [];
/** f runs each time my role steps down; `has` says what I still hold. */
export const onStaffLoss = (f: (has: (need: Need) => boolean) => void): void => void lost.push(f);

/** Notices a step down (called by the watcher below and before every check, so no answer slips in between). */
export function syncStaff(): void {
  const now = rank(), down = now < was;
  was = now; // first: a store's clearing may ask again (a moderator's inbox) and come back through here
  if (down) { epoch++; for (const f of lost) f((need) => now >= needs(need)); }
}

/** Taken before a staff request; called when its answer comes: true while the role held all the way through. */
export function staffStill(need: Need = 'admin'): () => boolean {
  // from the first staff request on, a step down is noticed as it happens, whatever page is open
  if (!watching && typeof window !== 'undefined') { watching = true; $effect.root(() => { $effect(() => { void session.me?.role; syncStaff(); }); }); }
  syncStaff();
  const at = epoch;
  return () => { syncStaff(); return at === epoch && rank() >= needs(need); };
}
