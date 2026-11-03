<script lang="ts">
  // All my clubs, pushed from the Clubs tab's "All" circle (3+ of them, owner Nov 3): the rows of its "I run" part, for
  // every club: my role there and what's next. A tap opens it as on the tab (a club I'm in its Studio, one I follow its page).
  // ponytail: the rows are the tab's at the tap, not live; fine for a list opened and left, derive here if it must update
  import type { OrgRef } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { shortOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import { TAB_ICON } from '../../ui/icons';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  let { overlay, rows }: { overlay: Overlay; rows: { org: OrgRef; role: string | null; sub: string }[] } = $props();
  const open = (x: { org: OrgRef; role: string | null }) => { haptic.tap(); if (x.role) sheets.studio(x.org.id); else sheets.club(x.org.id); };
</script>

<Pane {overlay} title={t('clubs.mineTitle')} icon={TAB_ICON.club}>
  <div class="list"><Group>
    {#each rows as x (x.org.id)}
      <Row dense title={shortOf(x.org)} subtitle={x.sub} accessory="chevron" onclick={() => open(x)}>
        {#snippet lead()}<OrgLogo org={x.org} size={40} />{/snippet}
      </Row>
    {/each}
  </Group></div>
</Pane>

<style>
  .list :global(.st) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
