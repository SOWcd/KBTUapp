<script lang="ts" module>
  import { dateInput, fromInputs, nowTs, time } from '../../lib/time';

  /** Wishlists close an hour before the gifts day at the latest (server santa.LEAD): the draw needs that moment. */
  export const LEAD = 3600;
  /** Wishlists until: a week before the gifts day; a game closer than that, halfway there (server santa.default_until). */
  export function defaultUntil(starts: number): number {
    return Math.min(starts - LEAD, starts - 7 * 86400 > nowTs() ? starts - 7 * 86400 : nowTs() + Math.floor((starts - nowTs()) / 2));
  }
  export const termsFrom = (budget: number | null | undefined, until: number) => ({ budget: budget ? String(budget) : '', day: dateInput(until), hm: time(until) });
  /** The fields read: the values to send, or what is wrong (bounds as the server's: 100 to 1 000 000 ₸, now < until ≤ the gifts day − an hour). */
  export function readTerms(f: { budget: string; day: string; hm: string }, starts: number) {
    const raw = f.budget.replace(/\s/g, ''), budget = raw ? Number(raw) : null, until = fromInputs(f.day, f.hm);
    return { budget, until, badBudget: budget !== null && !(Number.isInteger(budget) && budget >= 100 && budget <= 1_000_000),
             badUntil: !Number.isFinite(until) || until <= nowTs() || until > starts - LEAD };
  }
</script>

<script lang="ts">
  // Secret Santa's two settings (server santa.py): the gift's budget and the wishlists' deadline, at the start
  // (SantaHi) and until the draw (EventManage). Field's look; the date and time native (Field has no such type).
  import Field from '../../ui/Field.svelte';
  import { t } from '../../lib/i18n/index.svelte';

  let { f = $bindable(), starts, tried = false }: { f: { budget: string; day: string; hm: string }; starts: number; tried?: boolean } = $props();
  const r = $derived(readTerms(f, starts));
</script>

<div class="terms">
  <Field label="{t('santa.budget')}, ₸" bind:value={f.budget} inputmode="numeric" maxlength={9} placeholder={t('santa.budgetPh')} enterkeyhint="done"
    error={tried && r.badBudget ? t('santa.badBudget') : undefined} />
  <div class="two">
    <label class="fl" class:bad={tried && r.badUntil}><span>{t('santa.until')}</span><input type="date" bind:value={f.day} /></label>
    <label class="fl" class:bad={tried && r.badUntil}><span>{t('santa.untilTime')}</span><input type="time" bind:value={f.hm} /></label>
  </div>
  {#if tried && r.badUntil}<p class="err t-foot">{t('santa.badUntil')}</p>{/if}
</div>

<style>
  .terms { display: flex; flex-direction: column; gap: var(--s-3); width: 100%; text-align: left; }
  .two { display: grid; grid-template-columns: 3fr 2fr; gap: var(--s-2); }
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
  .fl.bad > input { box-shadow: inset 0 0 0 1.5px var(--danger); }
  .err { margin: 0; padding: 0 var(--s-4); color: var(--danger-text); }
</style>
