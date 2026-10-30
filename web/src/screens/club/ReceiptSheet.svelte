<script lang="ts">
  // One receipt of a paid event (SPEC §4.3), for the club's Head+: what the student sent and what was read off it, to
  // compare with the club's Kaspi history. "Reject": the ticket stops working, the seat goes to the waitlist and the bot
  // asks the student to talk to the club (money goes back outside the app). A flagged one can be passed.
  import { onDestroy } from 'svelte';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import { api, type AttendeeReceipt } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { ago, whenLine } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, receipt, name, ondone }: { overlay: Overlay; receipt: AttendeeReceipt; name: string; ondone?: () => void } = $props();

  let src = $state('');
  let failed = $state(false);
  $effect(() => { api.receiptImage(receipt.id).then((u) => (src = u)).catch(() => (failed = true)); });
  onDestroy(() => { if (src.startsWith('blob:')) URL.revokeObjectURL(src); });
  const flagged = $derived(receipt.flags.length > 0 && !receipt.reviewed);

  let busy = $state('');
  async function review(reject: boolean) {
    if (reject && !(await sheets.ask({ title: t('rc.rejectAsk', { name }), text: t('rc.rejectText'), ok: t('rc.reject'), cancel: t('common.cancel'), danger: true }))) return;
    busy = reject ? 'no' : 'ok';
    try {
      await api.reviewReceipt(receipt.id, reject);
      haptic.ok(); say(reject ? t('rc.rejected') : t('rc.passed'), reject ? 'waving_hand_3d_default' : 'raising_hands_3d_default');
      ondone?.();
      close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = ''; }
  }
</script>

<Sheet {overlay} tall title={t('rc.title')}>
  <h2 class="t-h2 hd">{name}</h2>
  <p class="t-foot">{t('rc.title')} · {ago(receipt.at)}</p>
  {#if flagged}{#each receipt.flags as f (f)}<p class="flag"><TriangleAlert size={16} />{f === 'recipient_mismatch'
    ? t('rc.flag.recipient_mismatch', { name: receipt.recipient ?? '' }) : t(`rc.flag.${f}` as 'rc.flag.duplicate')}</p>{/each}{/if}
  {#if receipt.amount || receipt.sender || receipt.paidAt}
    <div class="read surface">
      {#if receipt.amount}<div class="row"><i>{t('rc.amount')}</i><b class="num">{money(receipt.amount)}</b></div>{/if}
      {#if receipt.sender}<div class="row"><i>{t('rc.sender')}</i><b>{receipt.sender}</b></div>{/if}
      {#if receipt.paidAt}<div class="row"><i>{t('rc.paidAt')}</i><b>{whenLine(receipt.paidAt)}</b></div>{/if}
      {#if receipt.no}<div class="row"><i>{t('rc.no')}</i><b class="num no selectable">{receipt.no}</b></div>{/if}
    </div>
  {/if}
  <p class="t-foot hint">{t('rc.compare')}</p>
  <div class="img surface">
    {#if src}<img {src} alt={t('rc.title')} />{:else if failed}<p class="t-foot">{t('common.error')}</p>{:else}<span class="wait"></span>{/if}
  </div>

  {#snippet footer()}
    <div class="acts btns">
      {#if flagged}<Button kind="secondary" size="l" full loading={busy === 'ok'} onclick={() => review(false)}>{t('rc.ok')}</Button>{/if}
      <Button kind="danger" size="l" full loading={busy === 'no'} onclick={() => review(true)}>{t('rc.reject')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .flag { display: flex; align-items: center; gap: 6px; margin-top: 10px; padding: 8px 12px; border-radius: var(--r-m); background: var(--warning-soft);
    color: var(--warning-text); font: 650 14px/1.3 var(--font-text); }
  .read { display: flex; flex-direction: column; margin-top: 12px; padding: 2px 14px; }
  .row { display: flex; align-items: center; gap: 10px; min-height: 44px; }
  .row + .row { border-top: 1px solid var(--line); }
  .row i { flex: none; width: 104px; font: 550 13px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .row b { flex: 1; min-width: 0; font: 650 15px/1.3 var(--font-text); overflow-wrap: anywhere; }
  .num { font-variant-numeric: tabular-nums; }
  .no { font-size: 13.5px; letter-spacing: 0.01em; }
  .hint { margin: 10px 2px; }
  .img { display: flex; align-items: center; justify-content: center; min-height: 240px; padding: 6px; overflow: hidden; }
  .img img { display: block; max-width: 100%; height: auto; border-radius: var(--r-m); }
  .wait { width: 28px; height: 28px; border-radius: 50%; border: 3px solid var(--line-2); border-top-color: var(--accent); animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .acts { display: flex; gap: 8px; }
</style>
