<script lang="ts">
  // DMP's panel: every organisation's groups as one tree (organisation → main group → departments), collapsed to the
  // organisations with a one-line total each; a tap opens one. Counts only. Loaded with the registry (data.chatTrees).
  import type { Overlay } from '../../lib/state/ui.svelte';
  import Network from '@lucide/svelte/icons/network';
  import { data, loadChatTrees } from '../../lib/state/data.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import type { ChatTree as Tree, Id } from '../../lib/api';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import ChatTree from '../club/ChatTree.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  $effect(() => { void loadChatTrees(); }); // shown from the store at once, refreshed quietly
  // the organisations with groups; the ones the bot hasn't reached folded into one last row
  const list = $derived((data.chatTrees ?? []).filter((x) => x.groups > 0));
  const none = $derived((data.chatTrees ?? []).filter((x) => !x.groups));
  let noneOpen = $state(false);
  let open = $state<Id[]>([]);
  const toggle = (id: Id) => { haptic.select(); open = open.includes(id) ? open.filter((x) => x !== id) : [...open, id]; };
  const line = (x: Tree) => [tn('ct.groups', x.groups), x.kept ? t('ct.kept', { n: x.kept }) : '', x.last ? ago(x.last) : ''].filter(Boolean).join(' · ');
</script>

<Sheet {overlay} icon={Network} full title={t('ct.dmp')}>
  {#if !data.chatTrees}<Skeleton n={6} />
  {:else}
    <Group footnote={t('ct.dmpNote')}>
      {#each list as x (x.org.id)}
        <Row dense title={x.org.name} subtitle={line(x)} accessory="disclosure" open={open.includes(x.org.id)} onclick={() => toggle(x.org.id)}>
          {#snippet lead()}<OrgLogo org={x.org} size={28} />{/snippet}
        </Row>
        {#if open.includes(x.org.id)}<ChatTree tree={x} base={1} />{/if}
      {/each}
      {#if none.length}
        <Row dense title={t('ct.none')} value={String(none.length)} accessory="disclosure" open={noneOpen} onclick={() => { haptic.select(); noneOpen = !noneOpen; }} />
        {#if noneOpen}{#each none as x (x.org.id)}<Row dense title={x.org.name}>{#snippet lead()}<OrgLogo org={x.org} size={28} />{/snippet}</Row>{/each}{/if}
      {/if}
    </Group>
  {/if}
</Sheet>
