<script lang="ts">
  // The Student Government's panel (opened by its round button on the profile); its tools: the queue of appeals (its granted people only, server appeals.queue): open, overdue, closed; an anonymous one never
  // says who; "Solved by your appeals" to add and delete (Solved.svelte); the months' counts by topic (small ones merged
  // by the server). Loaded with the app, fresh on open. desk 'help': the help desk's queue of questions (its own people), no Solved.
  import { onMount, untrack } from 'svelte';
  import Inbox from '@lucide/svelte/icons/inbox';
  import Landmark from '@lucide/svelte/icons/landmark';
  import MessageCircleQuestion from '@lucide/svelte/icons/message-circle-question-mark';
  import type { Appeal } from '../../lib/api';
  import { data, loadAppeals, loadHelpq, loadSg } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { statusOf, lineOf, headOf, type Desk } from './Appeals.svelte';
  import Solved from './Solved.svelte';

  let { overlay, desk = 'sg' }: { overlay: Overlay; desk?: Desk } = $props();
  const sg = untrack(() => desk === 'sg');
  type F = 'open' | 'overdue' | 'closed';
  let f = $state<F>('open');
  onMount(() => { if (!sg) { void loadHelpq(); return; } void loadSg(); void loadAppeals(); }); // the Solved feed fresh too (another SG member's adds)
  const late = (a: Appeal) => a.overdue && a.status !== 'closed';
  const q = $derived(sg ? data.sg : data.helpq);
  const shown = $derived((q?.items ?? []).filter((a) => (f === 'closed' ? a.status === 'closed' : f === 'overdue' ? late(a) : a.status !== 'closed')));
</script>

<Sheet {overlay} title={t(sg ? 'apl.sg' : 'ask.queue')} icon={sg ? Landmark : MessageCircleQuestion} full>
  <div class="page">
    <Segmented bind:value={f} items={(['open', 'overdue', 'closed'] as F[]).map((v) => ({ value: v, label: t(`apl.f.${v}`) }))} />
    {#if shown.length}
      <Group footnote={t(sg ? 'apl.sgNote' : 'ask.note')}>
        {#each shown as a (a.id)}
          <Row dense title={headOf(a)} subtitle={`${statusOf(a)} · ${a.anon ? t('apl.anonAuthor') : a.author ?? ''} · ${lineOf(a)}`}
            accessory="chevron" onclick={() => { haptic.tap(); if (sg) sheets.sgAppeal(a.id); else sheets.helpAppeal(a.id); }} />
        {/each}
      </Group>
    {:else if q}
      <EmptyState icon={Inbox} title={t(sg ? 'apl.empty' : 'ask.empty')} inline />
    {/if}
    {#if sg}<Solved edit />{/if}
    {#if sg && q?.months.length}
      <Group caption={t('apl.months')}>
        {#each q.months as m (m.month)}
          <Row dense title={new Date(`${m.month}-15T12:00:00Z`).toLocaleDateString(i18n.lang, { month: 'long', year: 'numeric' })} subtitle={Object.entries(m.topics).map(([k, n]) => `${t(`apl.t.${k as 'other'}`)} ${n}`).join(' · ')} value={String(m.total)} />
        {/each}
      </Group>
    {/if}
  </div>
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
</style>
