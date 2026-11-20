// Admin's pages stay open only while I hold the role they need (a demoted admin kept the controls of
// the page he had open, the server refusing each tap). Called as a page is set up: the page closes the moment the
// role is gone (what the app held for the staff is cleared by the stores themselves: staffAccess's onStaffLoss).
import { session } from './session.svelte';
import { close, type Overlay } from './ui.svelte';

/** need: 'admin', or 'staff' for the pages a moderator has too. */
export function staffOnly(overlay: () => Overlay, need: 'admin' | 'staff' = 'admin'): void {
  $effect(() => {
    const role = session.me?.role;
    if (role === 'admin' || (need === 'staff' && role === 'moderator')) return;
    close(overlay().id);
  });
}
