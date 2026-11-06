<script lang="ts">
  // Admin → My notifications: one switch per work item the bot sends me (server STAFF_KINDS). Mine alone; muted by
  // every staff member, the creator still gets it (said in the footnote). The list comes with the app (data.staffMutes)
  // and is asked again as the page opens. A tap flips at once; each switch's saves go one after another, so the last
  // tap is what the server keeps, and a failed save rolls back only if no newer tap came since.
  import { untrack } from 'svelte';
  import { api, type StaffMute } from '../../lib/api';
  import { data, loadStaffMutes, mutedTap } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  untrack(loadStaffMutes); // in the background: the page shows what the app holds
  // the forum channel's two only while it is on
  const shown = $derived(data.staffMutes?.filter((m) => session.me?.forumChannel || !m.kind.startsWith('fch_')) ?? []);
  const queue: Record<string, Promise<unknown>> = {}, taps: Record<string, number> = {};
  const flip = (m: StaffMute, on: boolean) => {
    haptic.tap();
    mutedTap();
    m.on = on;
    const k = m.kind, n = (taps[k] = (taps[k] ?? 0) + 1);
    queue[k] = (queue[k] ?? Promise.resolve()).then(() => api.setStaffMute(k, on)).catch(() => {
      if (taps[k] !== n) return;
      m.on = !on;
      say(t('common.error'), 'warning_3d');
    });
  };
</script>

<Pane {overlay} title={t('adm.notify')}>
  {#if data.staffMutes}
    <Group footnote={t('adm.notify.note')}>
      {#each shown as m (m.kind)}
        <Row title={t(`adm.notify.${m.kind}` as 'adm.notify')} accessory="switch" checked={m.on} onchange={(on) => flip(m, on)} />
      {/each}
    </Group>
  {:else if data.staffMutesFailed}<EmptyState inline text={t('common.error')} onretry={loadStaffMutes} />
  {:else}<Skeleton n={4} />{/if}
</Pane>
