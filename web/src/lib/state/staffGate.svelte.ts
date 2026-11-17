// Admin's pages stay open only while I hold the role they need (review Nov 17: a demoted admin kept the controls of
// the page he had open, the server refusing each tap). Called as a page is set up: the page closes the moment the
// role is gone, and what the app held for the staff goes with it.
import { clearAdminOrgs } from './adminOrgs.svelte';
import { data } from './data.svelte';
import { session } from './session.svelte';
import { close, type Overlay } from './ui.svelte';

/** need: 'admin', or 'staff' for the pages a moderator has too. */
export function staffOnly(overlay: () => Overlay, need: 'admin' | 'staff' = 'admin'): void {
  $effect(() => {
    const role = session.me?.role;
    if (role === 'admin' || (need === 'staff' && role === 'moderator')) return;
    clearAdminOrgs(); data.adminStats = null; // the admin's alone
    if (role !== 'moderator') { data.inbox = null; data.staffMutes = null; }
    close(overlay().id);
  });
}
