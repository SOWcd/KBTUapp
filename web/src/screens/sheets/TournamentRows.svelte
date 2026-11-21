<script lang="ts">
  import { onMount } from 'svelte';
  import Trophy from '@lucide/svelte/icons/trophy';
  import ListTree from '@lucide/svelte/icons/list-tree';
  import { api, type EventBracket, type EventGroups, type Id } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { sheets } from '../../lib/state/sheets';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { id, manage, manageBracket = manage, standalone = false }: {
    id: Id; manage: boolean; manageBracket?: boolean; standalone?: boolean;
  } = $props();
  let groups = $state.raw<EventGroups>(), bracket = $state.raw<EventBracket>(), failed = $state(false);
  const groupsScored = $derived(groups?.groups.some((g) => g.matches.some((m) => m.home_score !== null)));
  const bracketScored = $derived(bracket && [bracket.upper, bracket.lower, bracket.final].some((stage) =>
    stage.some((r) => r.matches.some((m) => m.status === 'played'))));
  const groupsVisible = $derived(groups && (groups.groups.length > 0 || (manage && bracket && !bracketScored)));
  const bracketVisible = $derived(bracket && (bracket.upper.length > 0 || (manageBracket && groups && !groupsScored)));

  function showGroups(g: EventGroups) {
    groups = g;
    if (g.groups.length && bracket?.upper.length) bracket = { upper: [], lower: [], final: [], teams: [], winner: null };
  }
  function showBracket(b: EventBracket) {
    bracket = b;
    if (b.upper.length && groups?.groups.length) groups = { groups: [] };
  }
  async function load() {
    failed = false;
    const [g, b] = await Promise.allSettled([api.eventGroups(id), api.eventBracket(id)]);
    if (g.status === 'fulfilled') groups = g.value;
    if (b.status === 'fulfilled') bracket = b.value;
    failed = g.status === 'rejected' || b.status === 'rejected';
  }
  onMount(() => { void load(); });
</script>

{#snippet rows()}
  {#if groupsVisible && groups}
    <Row icon={Trophy} title={t('gr.title')} value={groups.groups.length ? String(groups.groups.length) : undefined}
      accessory="chevron" onclick={() => sheets.groups(id, manage, groups, showGroups, !!bracket?.upper.length)} />
  {/if}
  {#if bracketVisible && bracket}
    {@const seed = bracket}
    <Row icon={ListTree} title={t('br.title')} accessory="chevron" onclick={() => sheets.bracket(id, manageBracket, seed, showBracket)} />
  {/if}
  {#if failed}
    <Row icon={Trophy} title={t('br.loadError')} value={t('common.retry')} onclick={load} />
  {/if}
{/snippet}

{#if standalone}
  {#if failed || groupsVisible || bracketVisible}
    <Group>{@render rows()}</Group>
  {/if}
{:else}
  {@render rows()}
{/if}
