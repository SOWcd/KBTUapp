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
  import Button from '../../ui/Button.svelte';
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

<Sheet {overlay} tall title={t(`memo.${kind}`)}>
  <h2 class="t-h2">{t(`memo.${kind}`)}</h2>
  {#if timed}
    <label class="field"><span class="t-cap">{t('ed.date')}</span><input type="date" bind:value={f.date} min={dateInput(from)} /></label>
    <div class="two">
      <label class="field"><span class="t-cap">{t('ed.start')}</span><input type="time" bind:value={f.start} /></label>
      <label class="field"><span class="t-cap">{t('ed.end')}</span><input type="time" bind:value={f.end} /></label>
    </div>
    <label class="field"><span class="t-cap">{t('ed.place')}</span><input bind:value={f.place} maxlength="80" placeholder={t('memo.itemPlacePh')} /></label>
  {/if}
  <MemoAsksForm bind:memo={f.memo} seats="" date={f.date} only={kind} />
  {#if text}<h3 class="t-cap sec">{t('memo.itemPreview')}</h3><p class="preview surface">{text}</p>{/if}

  {#snippet footer()}
    <Button kind="primary" size="l" full disabled={!text} onclick={insert}>{t('memo.itemInsert')}</Button>
  {/snippet}
</Sheet>

<style>
  .field { margin-bottom: 10px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .sec { margin: 18px 2px 8px; }
  .preview { padding: 12px 14px; white-space: pre-wrap; font: 500 14px/1.45 var(--font-text); }
</style>
