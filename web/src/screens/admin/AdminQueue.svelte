<script lang="ts">
  // Admin → To decide, the admins' way in (owner, Nov 17: the sheet starts from its search; what waits is one row with
  // its count): the same queue and its Done list (AdminInbox), on a page of their own. A moderator, whose whole Admin
  // the queue is, keeps it on the sheet itself.
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Pane from '../../ui/Pane.svelte';
  import AdminInbox from './AdminInbox.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  staffOnly(() => overlay, 'staff');
</script>

<Pane {overlay} title={t('adm.queue')}>
  <div class="page"><AdminInbox /></div>
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
  .page :global(.sec > .hd) { display: none; } /* the page's title says it */
</style>
