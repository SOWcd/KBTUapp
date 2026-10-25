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

  let { overlay }: { overlay: Overlay } = $props();
  const today = dateInput(nowTs());
  const terms = TERMS.map((x) => ({ ...x, rows: [...x.rows].sort((a, b) => span(a)[0].localeCompare(span(b)[0])) }));
  const pastCount = terms.reduce((n, x) => n + x.rows.filter((r) => span(r)[1] < today).length, 0);
  let showPast = $state(false);
  const rowsOf = (rows: (typeof terms)[number]['rows']) => (showPast ? rows : rows.filter((r) => span(r)[1] >= today));
  const online = ONLINE.map((d) => { const [a, b = a] = d.split('/'); return dayRange(a, b); }).join(', ');
</script>

<Sheet {overlay} tall title={t('acad.title')}>
  <h2 class="t-h2 hd">{t('acad.title')}</h2>
  <p class="t-foot sub">{t('acad.sub')}</p>
  {#if pastCount}
    <button class="pastq" onclick={() => (showPast = !showPast)}>{showPast ? t('acad.hidePast') : t('acad.showPast', { n: pastCount })}</button>
  {/if}
  {#each terms.filter((x) => rowsOf(x.rows).length) as term (term.key)}
    <h3 class="t-cap gh">{t(`acad.${term.key}` as 'acad.fall')}{#if term.key === 'summer'}<span class="gn"> · {t('acad.summerNote')}</span>{/if}</h3>
    <div class="list surface">
      {#each rowsOf(term.rows) as r (r.key + r.at + (r.who ?? ''))}
        {@const [a, b] = span(r)}
        <div class="row" transition:fold class:past={b < today} class:now={a <= today && today <= b}>
          <span class="tx"><b>{nameOf(r)}</b>
            {#if r.who || (a <= today && today <= b)}<i>{#if a <= today && today <= b}<em>{t('acad.now')}</em>{/if}{#if r.who}<span class="who">{t(`acad.who.${r.who}` as 'acad.who.ise')}</span>{/if}</i>{/if}</span>
          <span class="dt">{whenOf(r)}</span>
        </div>
      {/each}
    </div>
  {/each}
  <p class="t-foot note">{t('acad.online', { days: online })}</p>
  <p class="t-foot note">{t('acad.source')}</p>
</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .sub { margin-bottom: 6px; }
  .gh { margin: 18px 4px 8px; }
  .gn { text-transform: none; letter-spacing: 0; font-weight: 500; }
  .list { display: flex; flex-direction: column; padding: 2px 0; }
  .row { display: flex; align-items: center; gap: 12px; padding: 11px 14px; }
  .row + .row { border-top: 1px solid var(--line); }
  .row.past { opacity: 0.45; }
  .row.now { box-shadow: inset 3px 0 0 var(--accent); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
  .tx b { font: 600 15px/1.25 var(--font-text); }
  .tx i { display: flex; gap: 6px; font-style: normal; }
  .tx em, .who { padding: 2px 7px; border-radius: 6px; font: 650 11.5px/1.3 var(--font-text); font-style: normal; }
  .tx em { background: var(--accent); color: #fff; }
  .who { background: var(--surface-2); color: var(--text-2); }
  .dt { flex: none; max-width: 46%; text-align: right; font: 600 14px/1.3 var(--font-text); color: var(--text-2); font-variant-numeric: tabular-nums; }
  .now .dt { color: var(--accent-text); }
  .note { margin: 14px 4px 0; }
  .pastq { align-self: flex-start; margin: 10px 4px 0; padding: 4px 0; font: 620 13.5px/1 var(--font-text); color: var(--accent-text); }
</style>
