<script lang="ts">
  // A club of mine, its Studio pushed from the right over the Clubs tab (round 5: the tab is one feed; my club's card
  // opens this, Telegram's Back closes it). Each club its own pane: Studio and Team read the club from ui.club.
  import { untrack } from 'svelte';
  import Pane from '../../ui/Pane.svelte';
  import Studio from './Studio.svelte';
  import { ui, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { nameOf } from '../../lib/short';
  import { TAB_ICON } from '../../ui/icons';

  let { overlay, org }: { overlay: Overlay; org: number } = $props();
  ui.club = untrack(() => org);
  const m = $derived(session.me?.memberships.find((x) => x.org.id === org));
</script>

<Pane {overlay} bare title={m ? nameOf(m.org) : ''} icon={TAB_ICON.club}><Studio onTitle={(gone) => (overlay.quiet = !gone)} /></Pane>
