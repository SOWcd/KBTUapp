<script lang="ts">
  // SG's queue of appeals (its granted people only, server appeals.queue): open, overdue, closed; an anonymous one never
  // says who; the months' counts by topic (small ones merged by the server). Loaded with the app, fresh on open.
  import { onMount } from 'svelte';
  import Inbox from '@lucide/svelte/icons/inbox';
  import type { Appeal } from '../../lib/api';
  import { data, loadSg } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { statusOf, lineOf, headOf } from './Appeals.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  type F = 'open' | 'overdue' | 'closed';
  let f = $state<F>('open');
  onMount(() => { void loadSg(); });
  const late = (a: Appeal) => a.overdue && a.status !== 'closed';
  const shown = $derived((data.sg?.items ?? []).filter((a) => (f === 'closed' ? a.status === 'closed' : f === 'overdue' ? late(a) : a.status !== 'closed')));
</script>

<Sheet {overlay} heading={t('apl.sgRow')} icon={Inbox} full>
  <div class="page">
    <Segmented bind:value={f} items={(['open', 'overdue', 'closed'] as F[]).map((v) => ({ value: v, label: t(`apl.f.${v}`) }))} />
    {#if shown.length}
      <Group footnote={t('apl.sgNote')}>
        {#each shown as a (a.id)}
          <Row dense title={headOf(a)} subtitle={`${statusOf(a)} · ${a.anon ? t('apl.anonAuthor') : a.author ?? ''} · ${lineOf(a)}`}
            accessory="chevron" onclick={() => { haptic.tap(); sheets.sgAppeal(a.id); }} />
        {/each}
      </Group>
    {:else if data.sg}
      <EmptyState icon={Inbox} title={t('apl.empty')} inline />
    {/if}
    {#if data.sg?.months.length}
      <Group caption={t('apl.months')}>
        {#each data.sg.months as m (m.month)}
          <Row dense title={new Date(`${m.month}-15T12:00:00Z`).toLocaleDateString(i18n.lang, { month: 'long', year: 'numeric' })} subtitle={Object.entries(m.topics).map(([k, n]) => `${t(`apl.t.${k as 'other'}`)} ${n}`).join(' · ')} value={String(m.total)} />
        {/each}
      </Group>
    {/if}
  </div>
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
</style>
