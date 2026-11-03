<script lang="ts">
  // One item of the memo without an event ("+ Room", "+ Guests"...): that request's fields, the day and
  // hours, and the paragraph the server writes from them, shown live; "Insert" puts it in the memo's text.
  import { untrack } from 'svelte';
  import { api, type Id, type MemoAsks } from '../../lib/api';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { dateInput, fromInputs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import StickyNote from '@lucide/svelte/icons/sticky-note';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import MemoAsksForm from './MemoAsks.svelte';

  // from: the memo's week (next Monday; from Thursday the one after)
  let { overlay, org, kind, from, oninsert }: { overlay: Overlay; org: Id; kind: keyof MemoAsks; from: number; oninsert: (text: string) => void } = $props();

  let f = $state({ date: dateInput(untrack(() => from) + 86400), start: '18:00', end: '21:00', place: '', memo: {} as MemoAsks });
  const timed = $derived(kind === 'room' || kind === 'guests' || kind === 'provide'); // the others have their own dates
  let text = $state('');
  // the paragraph, a moment after the last change
  $effect(() => {
    const body = { kind, fields: $state.snapshot(f.memo[kind]) ?? {}, place: f.place, startsAt: fromInputs(f.date, f.start), endsAt: fromInputs(f.date, f.end) || null };
    if (!Number.isFinite(body.startsAt)) return;
    if (!(body.endsAt! > body.startsAt)) body.endsAt = null;
    const id = setTimeout(() => api.memoItem(org, body).then((r) => (text = r)).catch(() => (text = '')), 250);
    return () => clearTimeout(id);
  });
  function insert() { if (!text) return; haptic.ok(); oninsert(text); close(overlay.id); }
</script>

<Sheet {overlay} icon={StickyNote} tall title={t(`memo.${kind}`)}>
  <div class="stack">
    {#if timed}
      <!-- engine: Field has no date/time type (nor min): by hand, in Field's look (.fl) -->
      <label class="fl"><span>{t('ed.date')}</span><input type="date" bind:value={f.date} min={dateInput(from)} /></label>
      <div class="two">
        <label class="fl"><span>{t('ed.start')}</span><input type="time" bind:value={f.start} /></label>
        <label class="fl"><span>{t('ed.end')}</span><input type="time" bind:value={f.end} /></label>
      </div>
      <Field label={t('ed.place')} bind:value={f.place} maxlength={80} placeholder={t('memo.itemPlacePh')} />
    {/if}
    <MemoAsksForm bind:memo={f.memo} seats="" date={f.date} only={kind} />
    {#if text}<h3 class="lbl">{t('memo.itemPreview')}</h3><p class="preview">{text}</p>{/if}
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full disabled={!text} onclick={insert}>{t('memo.itemInsert')}</Button>
  {/snippet}
</Sheet>

<style>
  .stack { display: flex; flex-direction: column; gap: var(--s-3); }
  .two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); }
  .lbl { margin: var(--s-3) var(--s-4) -6px; font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .preview { padding: var(--s-3) var(--s-4); border-radius: var(--r-group); background: var(--surface); white-space: pre-wrap; font: 450 var(--fs-body)/1.45 var(--font-text); }
  /* Field's look for the date and time inputs it can't take yet */
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
</style>
