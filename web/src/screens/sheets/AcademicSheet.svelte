<script lang="ts">
  // KBTU's academic calendar (SPEC §4.11): the year's dates by semester, each in order; what is on says so. What is over
  // stays out of the way: one quiet line on top brings it back, faded,
  // in its place. The PDF's footnote (classes held online) and its source at the end.
  import { fold } from '../../ui/fold';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { TERMS, ONLINE, span, nameOf, whenOf } from '../../lib/academic';
  import { dateInput, dayRange, nowTs } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const today = dateInput(nowTs());
  const terms = TERMS.map((x) => ({ ...x, rows: [...x.rows].sort((a, b) => span(a)[0].localeCompare(span(b)[0])) }));
  const pastCount = terms.reduce((n, x) => n + x.rows.filter((r) => span(r)[1] < today).length, 0);
  let showPast = $state(false);
  const rowsOf = (rows: (typeof terms)[number]['rows']) => (showPast ? rows : rows.filter((r) => span(r)[1] >= today));
  const online = ONLINE.map((d) => { const [a, b = a] = d.split('/'); return dayRange(a, b); }).join(', ');
</script>

<Sheet {overlay} icon={GraduationCap} tall title={t('acad.title')}>
  <p class="t-foot">{t('acad.sub')}</p>
  {#if pastCount}
    <div class="pastq"><Button kind="plain" size="s" onclick={() => (showPast = !showPast)}>{showPast ? t('acad.hidePast') : t('acad.showPast', { n: pastCount })}</Button></div>
  {/if}
  <div class="terms">
    {#each terms.filter((x) => rowsOf(x.rows).length) as term (term.key)}
      <Group caption={t(`acad.${term.key}` as 'acad.fall') + (term.key === 'summer' ? ' · ' + t('acad.summerNote') : '')}>
        {#each rowsOf(term.rows) as r (r.key + r.at + (r.who ?? ''))}
          {@const [a, b] = span(r)}
          <!-- engine: ui/Group draws its lines only between Rows that are siblings; a row folding in place needs a wrapper -->
          <div class="it" transition:fold class:past={b < today}>
            <Row dense title={nameOf(r)} subtitle={[whenOf(r), r.who ? t(`acad.who.${r.who}` as 'acad.who.ise') : ''].filter(Boolean).join(' · ')}>
              {#snippet detail()}{#if a <= today && today <= b}<Tag tone="accent">{t('acad.now')}</Tag>{/if}{/snippet}
            </Row>
          </div>
        {/each}
      </Group>
    {/each}
  </div>
  <p class="t-foot note">{t('acad.online', { days: online })}</p>
  <p class="t-foot note">{t('acad.source')}</p>
</Sheet>

<style>
  .pastq { margin: var(--s-1) 0 0 calc(-1 * var(--s-2)); }
  .terms { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-4); }
  .it { position: relative; }
  .it + .it::before { content: ''; position: absolute; z-index: 1; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .it.past { opacity: 0.45; }
  .note { margin: 14px var(--s-1) 0; }
</style>
