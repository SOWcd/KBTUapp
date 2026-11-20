<script lang="ts">
  // A club of mine, its Studio pushed from the right over the Clubs tab (the tab is one feed; my club's card
  // opens this, Telegram's Back closes it). Each club its own pane: Studio and Team read the club from ui.club.
  // asCreator: the creator opened it from Admin (lib/state/creator): the club's membership stands in his list meanwhile.
  import { untrack } from 'svelte';
  import Pane from '../../ui/Pane.svelte';
  import Studio from './Studio.svelte';
  import { ui, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { closeCreator, creator, viewAs } from '../../lib/state/creator.svelte';
  import { staffOrg } from '../../lib/api';
  import { nameOf } from '../../lib/short';
  import { TAB_ICON } from '../../ui/icons';

  let { overlay, org, asCreator = false }: { overlay: Overlay; org: number; asCreator?: boolean } = $props();
  ui.club = untrack(() => org);
  const real = untrack(() => session.me?.memberships.find((x) => x.org.id === org));
  // in his list again whenever /api/me comes back (it carries only his own) or he views it as another role
  $effect(() => {
    const me = session.me, m = asCreator && creator.org === org ? viewAs() : null;
    if (me && m) untrack(() => { me.memberships = [...me.memberships.filter((x) => x.org.id !== org), m]; });
  });
  // the club's own events go as its President's (X-Staff-Org); one it co-hosts stays its host's
  $effect(() => { if (asCreator && creator.org === org) for (const e of data.studio[org] ?? []) if (e.org.id === org) staffOrg.events.add(e.id); });
  $effect(() => () => { if (asCreator) closeCreator(org, real); });
  const m = $derived(session.me?.memberships.find((x) => x.org.id === org));
</script>

<Pane {overlay} bare title={m ? nameOf(m.org) : ''} icon={TAB_ICON.club}><Studio onTitle={(gone) => (overlay.quiet = !gone)} /></Pane>
