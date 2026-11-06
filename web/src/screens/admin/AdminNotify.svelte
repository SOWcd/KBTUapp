<script lang="ts">
  // Admin → My notifications: one switch per work item the bot sends me (server STAFF_KINDS). Mine alone; muted by
  // every staff member, the creator still gets it (said in the footnote). A tap flips at once, the server follows.
  import { api, type StaffMute } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let list = $state<StaffMute[] | null>(null);
  $effect(() => { api.staffMutes().then((l) => (list = l)).catch(() => say(t('common.error'), 'warning_3d')); });
  // the forum channel's two only while it is on
  const shown = $derived(list?.filter((m) => session.me?.forumChannel || !m.kind.startsWith('fch_')) ?? []);
  const flip = (m: StaffMute, on: boolean) => {
    haptic.tap();
    m.on = on;
    api.setStaffMute(m.kind, on).catch(() => { m.on = !on; say(t('common.error'), 'warning_3d'); });
  };
</script>

<Pane {overlay} title={t('adm.notify')}>
  {#if list}
    <Group footnote={t('adm.notify.note')}>
      {#each shown as m (m.kind)}
        <Row title={t(`adm.notify.${m.kind}` as 'adm.notify')} accessory="switch" checked={m.on} onchange={(on) => flip(m, on)} />
      {/each}
    </Group>
  {:else}<Skeleton n={4} />{/if}
</Pane>
