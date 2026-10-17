<script lang="ts">
  // Paying for a seat (SPEC §4.3): the money goes straight to the club by Kaspi, never through the app. "Going · N ₸"
  // holds the seat for 30 minutes; the receipt makes it a ticket at once (the organizer compares it with their Kaspi
  // history and can still reject it). The receipt comes as Kaspi's PDF or a screenshot, here or through the bot
  // (Kaspi → Share → Telegram → the bot): back in the app after that, the seat that became a ticket opens it. A receipt
  // that looks wrong (the server's flags) keeps the ticket and says why at once, with another file to send in its place
  // until the organizer looks at it (owner, Oct 11); the ticket opens this sheet for that too.
  // ponytail: no "Open Kaspi" button: Kaspi has no public link that opens a transfer, so the number is one tap to copy.
  import { onMount } from 'svelte';
  import Copy from '@lucide/svelte/icons/copy';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import { api, ApiErr, type EventFull, type Id } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { eventById, eventDetails, put, toggleGoing } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { time, nowTs } from '../../lib/time';
  import { haptic, on } from '../../lib/tg';
  import { shrink } from '../../lib/photo';
  import { fmtPhone } from '../../lib/phone';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { burst } from '../../ui/burst';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  const e = $derived(eventById(id));
  let detail = $state<EventFull | null>(null);
  $effect(() => { eventDetails(id).then((x) => (detail = x)).catch(() => {}); });
  const until = $derived(e?.my?.holdUntil ?? null);
  const doubt = $derived(e?.my?.status === 'going' ? (e.my.receiptFlags ?? []) : []);
  const phone = $derived(fmtPhone(detail?.payPhone ?? ''));

  async function copy() {
    try { await navigator.clipboard.writeText(phone); haptic.ok(); say(t('pay.copied'), 'sparkles_3d'); }
    catch { haptic.error(); } // the number is selectable too
  }

  let busy = $state(false);
  let picker = $state<HTMLInputElement>();
  function paid() {
    haptic.ok(); burst(false, undefined, e?.emoji); say(t('pay.done'), 'party_popper_3d'); // the ticket: a moment (owner's list)
    close(overlay.id);
    sheets.ticket(id);
  }
  async function upload(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, file = el.files?.[0];
    el.value = '';
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'pleading_face_3d'); return; }
    busy = true;
    try {
      const c = await api.uploadReceipt(id, await shrink(file, 2400)); // a PDF goes as it is (shrink can't draw it); OCR wants the detail
      put(c);
      if (c.my?.receiptFlags?.length) haptic.warn(); // the sheet now says why
      else paid();
    } catch (x) {
      haptic.error();
      say(x instanceof ApiErr && x.code === 'closed' ? t('pay.expired') : x instanceof ApiErr && x.message === 'not_receipt' ? t('pay.notReceipt') : x instanceof ApiErr && x.code === 'bad_input' ? t('ed.photoBad') : t('common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
  function release() { toggleGoing(id); close(overlay.id); }
  function keep() { close(overlay.id); sheets.ticket(id); }

  // the receipt went to the bot while the app waited in the background: back here, the ticket opens by itself
  async function recheck() {
    if (busy || document.hidden || eventById(id)?.my?.status !== 'hold') return;
    try {
      const x = await api.event(id);
      if (x.my?.status === 'going') { put(x); paid(); }
    } catch { /* offline: the next return checks again */ }
  }
  onMount(() => {
    document.addEventListener('visibilitychange', recheck);
    const off = on('activated', recheck);
    return () => { document.removeEventListener('visibilitychange', recheck); off(); };
  });
</script>

<Sheet {overlay} title={doubt.length ? t('pay.doubtTitle') : t('pay.title')}>
  {#if e && doubt.length}
    <p class="t-callout lead">{t('pay.doubtLead')}</p>
    {#each doubt as f (f)}<p class="flag"><TriangleAlert size={16} />{f === 'recipient_mismatch' ? t('pay.flagTo', { name: detail?.payToName ?? '…' })
      : t(`rc.flag.${f}` as 'rc.flag.duplicate')}</p>{/each}
    <p class="t-foot note">{t('pay.doubtNote')}</p>
  {:else if e}
    <h2 class="t-h2 hd">{money(e.price ?? 0)}</h2>
    <p class="t-foot ev ellipsis">{e.title}</p>
    <p class="t-callout lead">{t('pay.lead', { price: money(e.price ?? 0) })}</p>
    <div class="card surface">
      <div class="row"><i>{t('pay.to')}</i><b class="selectable">{detail?.payToName ?? '…'}</b></div>
      <div class="row"><i>{t('pay.phone')}</i><b class="selectable num">{phone || '…'}</b>
        {#if phone}<button class="cp" onclick={copy} aria-label={t('pay.copy')}><Copy size={18} /></button>{/if}</div>
    </div>
    {#if until}<p class="until" class:late={until < nowTs()}>{until < nowTs() ? t('pay.expired') : t('pay.until', { time: time(until) })}</p>{/if}
    <p class="bot"><TelegramMark size={18} /><span>{t('pay.bot')}</span></p>
    <p class="t-foot note">{t('pay.note')}</p>
    <button class="rel" onclick={release}>{t('pay.release')}</button>
  {/if}

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={() => picker?.click()}>{#snippet icon()}<ReceiptIcon size={18} />{/snippet}{doubt.length ? t('pay.another') : t('pay.upload')}</Button>
    {#if doubt.length}<button class="rel" onclick={keep}>{t('pay.keep')}</button>{/if}
    <input type="file" accept="image/*,application/pdf" hidden bind:this={picker} onchange={upload} />
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 0; }
  .ev { margin-top: 2px; }
  .lead { margin: 12px 0; color: var(--text-2); }
  .card { display: flex; flex-direction: column; padding: 4px 14px; }
  .row { display: flex; align-items: center; gap: 10px; min-height: 52px; }
  .row + .row { border-top: 1px solid var(--line); }
  .row i { flex: none; width: 96px; font: 550 13px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .row b { flex: 1; min-width: 0; font: 650 16px/1.3 var(--font-text); }
  .num { font-variant-numeric: tabular-nums; letter-spacing: 0.01em; }
  .cp { flex: none; width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text); }
  .cp:active { transform: scale(0.92); }
  .until { margin: 12px 2px 0; font: 650 14px/1.3 var(--font-text); color: var(--warning-text); }
  .until.late { color: var(--danger-text); }
  .bot { display: flex; align-items: flex-start; gap: 10px; margin: 14px 0 0; padding: 12px 14px; border-radius: var(--r-m);
    background: var(--accent-soft); color: var(--text); font: 550 14.5px/1.35 var(--font-text); }
  .bot :global(svg) { flex: none; margin-top: 1px; }
  .note { margin: 8px 2px 0; }
  .rel { display: block; margin: 14px auto 4px; padding: 6px 10px; font: 620 14px/1 var(--font-text); color: var(--text-2); }
  .flag { display: flex; align-items: flex-start; gap: 8px; margin: 0 0 8px; padding: 10px 12px; border-radius: var(--r-m);
    background: var(--warning-soft); color: var(--warning-text); font: 600 14.5px/1.35 var(--font-text); }
  .flag :global(svg) { flex: none; margin-top: 2px; }
</style>
