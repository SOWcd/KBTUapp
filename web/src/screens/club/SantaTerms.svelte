<script lang="ts" module>
  import { dateInput, fromInputs, nowTs, time } from '../../lib/time';

  /** Wishlists close an hour before the gifts day at the latest (server santa.LEAD): the draw needs that moment. */
  export const LEAD = 3600;
  /** Wishlists until: a week before the gifts day; a game closer than that, halfway there (server santa.default_until). */
  export function defaultUntil(starts: number): number {
    return Math.min(starts - LEAD, starts - 7 * 86400 > nowTs() ? starts - 7 * 86400 : nowTs() + Math.floor((starts - nowTs()) / 2));
  }
  /** budget: digits as typed; day, hm: the wishlists' deadline; gDay, gHm: the gifts day; touched: the deadline was set by hand */
  export type Terms = { budget: string; day: string; hm: string; gDay: string; gHm: string; touched: boolean };
  const group = (digits: string) => digits.replace(/\B(?=(\d{3})+$)/g, ' ');
  export const termsFrom = (budget: number | null | undefined, until: number, starts: number): Terms =>
    ({ budget: budget ? group(String(budget)) : '', day: dateInput(until), hm: time(until), gDay: dateInput(starts), gHm: time(starts), touched: false });
  /** One tap instead of typing: what students here usually agree on (a small thing, the usual, a generous one). */
  export const SUMS = [3000, 5000, 10000];
  /** The fields read: the values to send, or what is wrong (bounds as the server's: a sum of 100 to 1 000 000 ₸, now < until ≤ the gifts day − an hour). */
  export function readTerms(f: Terms) {
    const raw = f.budget.replace(/\s/g, ''), budget = raw ? Number(raw) : null, until = fromInputs(f.day, f.hm), starts = fromInputs(f.gDay, f.gHm);
    const badStarts = !(starts > nowTs());
    // why the deadline is wrong, in the order a person fixes it
    const untilErr = !Number.isFinite(until) || until <= nowTs() ? 'santa.untilPast' as const : until > starts - LEAD ? 'santa.untilLate' as const : null;
    const badBudget = budget !== null && !(Number.isInteger(budget) && budget >= 100 && budget <= 1_000_000);
    return { budget, until, starts, badBudget, badStarts, untilErr, badUntil: !!untilErr, bad: budget === null || badBudget || badStarts || !!untilErr };
  }
</script>

<script lang="ts">
  // Secret Santa's settings (server santa.py) as one Settings-like card: the gift's limit, the wishlists' deadline and
  // the gifts day; at the start (SantaHi: all three) and until the draw (EventManage: `fixed`, the gifts day is the
  // event's own start, changed in the editor). Dates as the event editor's: the app's own words in a pill, the
  // phone's picker under it. The deadline follows the gifts day until a hand sets it.
  import { t, money } from '../../lib/i18n/index.svelte';
  import { sw } from '../../lib/i18n/staff';
  import { haptic } from '../../lib/tg';
  import { dayMonthShort } from '../../lib/time';

  let { f = $bindable(), fixed = false }: { f: Terms; fixed?: boolean } = $props();
  const r = $derived(readTerms(f));
  let typing = $state(false); // a sum half typed is not an error yet
  // no sum yet is not a mistake: the line asks for it in grey, and only a wrong value is red
  const why = $derived(r.badBudget && !typing ? t('santa.badBudget') : r.badStarts ? t('santa.dayPast') : r.untilErr ? t(r.untilErr) : r.budget === null ? t('santa.needBudget') : '');
  const ask = $derived(r.budget === null && !r.badStarts && !r.untilErr);
  const day = (ts: number) => (Number.isFinite(ts) ? dayMonthShort(ts) : '—');

  function follow() {
    if (f.touched || !(r.starts > nowTs() + LEAD)) return;
    const u = defaultUntil(r.starts);
    f.day = dateInput(u); f.hm = time(u);
  }
</script>

<div class="terms">
  <div class="card">
    <label class="row" class:bad={r.badBudget && !typing}>
      <b>{t('santa.budgetTo')}</b>
      <input class="sum" bind:value={() => f.budget, (v) => (f.budget = group(v.replace(/\D/g, '').slice(0, 7)))} inputmode="numeric" maxlength={9}
        placeholder={t('santa.sumPh')} enterkeyhint="done" onfocus={() => (typing = true)} onblur={() => (typing = false)} />
      {#if f.budget}<span class="cur">₸</span>{/if}
    </label>
    <div class="sums">
      {#each SUMS as n (n)}
        <button type="button" class="tv" class:on={r.budget === n} aria-pressed={r.budget === n} onclick={() => { haptic.tap(); f.budget = group(String(n)); }}>{money(n)}</button>
      {/each}
    </div>
    <div class="row" class:bad={r.badUntil && !r.badStarts} onchange={() => (f.touched = true)}>
      <b>{t('santa.until')}</b>
      <label class="tv">{day(r.until)}<input type="date" bind:value={f.day} min={dateInput(nowTs())} max={fixed ? f.gDay : undefined} aria-label={t('santa.until')} /></label>
      <label class="tv">{f.hm || '—'}<input type="time" bind:value={f.hm} aria-label={sw('ed.time')} /></label>
    </div>
    <div class="row" class:bad={r.badStarts} onchange={follow}>
      <b>{t('santa.day')}</b>
      {#if fixed}<span class="val">{day(r.starts)}, {f.gHm}</span>
      {:else}
        <label class="tv">{day(r.starts)}<input type="date" bind:value={f.gDay} min={dateInput(nowTs())} aria-label={t('santa.day')} /></label>
        <label class="tv">{f.gHm || '—'}<input type="time" bind:value={f.gHm} aria-label={sw('ed.time')} /></label>
      {/if}
    </div>
  </div>
  <!-- the line's room is always there: the sheet stays still when it speaks -->
  <p class="why" class:ask role="status">{why}</p>
</div>

<style>
  .terms { width: 100%; text-align: left; }
  .card { display: flex; flex-direction: column; overflow: hidden; border-radius: var(--r-group); background: var(--group-bg, var(--surface)); box-shadow: var(--card-rim, none); }
  .row { position: relative; display: flex; align-items: center; gap: var(--s-2); min-height: var(--row-h); padding: 0 var(--s-3) 0 var(--s-4); }
  .row + .row::before, .sums + .row::before { content: ''; position: absolute; left: var(--s-4); right: 0; top: 0; height: 0.5px; background: var(--separator); }
  .row b { flex: 1 1 auto; min-width: 0; font: var(--fw-row) var(--fs-row)/1.25 var(--font-text); color: var(--text); overflow-wrap: anywhere; }
  /* the sum: typed at the row's end, 17 px (16 or more keeps iOS from zooming in) */
  .sum { flex: 1 1 0; width: 0; min-width: 6ch; align-self: stretch; padding: 0; background: none; text-align: right; color: var(--text);
    font: 600 var(--fs-row)/1.25 var(--font-text); font-variant-numeric: tabular-nums; }
  .sum::placeholder { color: var(--text-3); font-weight: 450; }
  label.row b { flex: 0 0 auto; }
  .cur, .sum:placeholder-shown { padding-right: var(--s-1); }
  .cur { flex: none; color: var(--text-2); font: 600 var(--fs-row)/1.25 var(--font-text); }
  .val { flex: none; padding-right: var(--s-1); color: var(--text-2); font: 450 var(--fs-row)/1.25 var(--font-text); white-space: nowrap; }
  /* EventEditor's .tv: the value in the app's language, the phone's own picker lying over it */
  .tv { position: relative; flex: none; padding: 8px var(--s-2); border-radius: var(--r-xs); background: var(--fill); color: var(--text); font: 600 var(--fs-body)/1 var(--font-text);
    font-variant-numeric: tabular-nums; white-space: nowrap; transition: background-color var(--t-fast); }
  .tv:active { background: var(--surface-3); }
  /* the usual sums under the row they fill, no line between: one thing */
  .sums { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-2); padding: 0 var(--s-3) var(--s-3) var(--s-4); }
  .sums .tv { padding-block: 10px; text-align: center; }
  .sums .tv::after { content: ''; position: absolute; inset: -5px 0; } /* 44 to the finger */
  .sums .on { background: var(--accent-soft); color: var(--accent-text); }
  .tv input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; }
  .bad .tv, .bad .sum, .bad .cur { color: var(--danger-text); }
  /* 320 px: "the gifts day" and both pills on one line */
  @media (max-width: 340px) { .row { gap: 6px; padding-right: var(--s-2); } .tv { padding-inline: 6px; } }
  .why { min-height: 1.4em; margin: var(--s-2) var(--s-4) 0; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--danger-text); }
  .why.ask { color: var(--text-3); }
</style>
