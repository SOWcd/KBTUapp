<script lang="ts">
  // The subjects (Forum tab's row): a search over the university's ~500 (name or code, any case and keyboard), and
  // before a word is typed, mine (my timetable's classes and the ones I'm listed on) and the ones people are looking on
  // now. A row's end says how many are looking; a tap opens its card. The list came with the app (state/subjects).
  import BookOpen from '@lucide/svelte/icons/book-open';
  import type { Subject } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { data } from '../../lib/state/data.svelte';
  import { subj, subjIndex, subjectCard } from '../../lib/state/subjects.svelte';
  import { subjectOf } from '../../lib/subjects';
  import { hit } from '../../lib/search';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let q = $state('');
  const all = $derived(subj.all?.subjects ?? []);
  const counts = $derived(subj.all?.counts ?? {});
  const found = $derived(q.trim() ? all.filter((s) => hit(q, [s.name, ...s.codes])).slice(0, 60) : []);
  const mine = $derived.by(() => {
    const idx = subjIndex(), ids = [...(subj.all?.mine ?? []), ...data.schedule.map((c) => subjectOf(c, idx)?.id)];
    return all.filter((s) => ids.includes(s.id));
  });
  const looking = $derived(all.filter((s) => counts[s.id] && !mine.includes(s)).sort((a, b) => counts[b.id] - counts[a.id]).slice(0, 30));
  const go = (s: Subject) => { haptic.tap(); sheets.subject(s.id); };
</script>

{#snippet rows(list: Subject[], caption?: string)}
  <!-- the card's people asked for as the finger lands (the row under it, by its place: Rows stay siblings for their lines) -->
  <div class="g" role="group" onpointerdown={(e) => { const r = (e.target as Element).closest('.kb-row'), s = r && list[[...e.currentTarget.querySelectorAll('.kb-row')].indexOf(r)]; if (s) void subjectCard(s.id).catch(() => {}); }}>
    <Group {caption}>
      {#each list as s (s.id)}
        <Row dense title={s.name} subtitle={s.codes.join(' · ') || undefined} value={counts[s.id] ? tn('sj.n', counts[s.id]) : undefined} whole accessory="chevron" onclick={() => go(s)} />
      {/each}
    </Group>
  </div>
{/snippet}

<Sheet {overlay} tall title={t('sj.title')} icon={BookOpen}>
  <div class="col">
    <SearchField bind:value={q} placeholder={t('sj.search')} />
    {#if q.trim()}
      {#if found.length}{@render rows(found)}
      {:else}<EmptyState inline text={t('sj.nothing')} />{/if}
    {:else}
      {#if mine.length}{@render rows(mine, t('sj.mine'))}{/if}
      {#if looking.length}{@render rows(looking, t('sj.looking'))}{/if}
      {#if !mine.length && !looking.length}<EmptyState icon={BookOpen} text={t('sj.hint')} />{/if}
    {/if}
  </div>
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--gap-group); padding-bottom: var(--s-6); }
</style>
