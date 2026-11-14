<script lang="ts">
  // Paying for a seat (SPEC §4.3): the money goes straight to the club by Kaspi, never through the app. "Going · N ₸"
  // holds the seat for 30 minutes; the receipt makes it a ticket at once (the organizer compares it with their Kaspi
  // history and can still reject it). The receipt comes as Kaspi's PDF or a screenshot, here or through the bot
  // (Kaspi → Share → Telegram → the bot): back in the app after that, the seat that became a ticket opens it. A receipt
  // that looks wrong (the server's flags) keeps the ticket and says why at once, with another file to send in its place
  // until the organizer looks at it; the ticket opens this sheet for that too.
  // ponytail: no "Open Kaspi" button: Kaspi has no public link that opens a transfer, so the number is one tap to copy.
  import { copyText } from '../../ui/copy';
  import { onMount } from 'svelte';
  import Copy from '@lucide/svelte/icons/copy';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import { api, ApiErr, type EventFull, type Id } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { eventById, put, toggleGoing } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { time, nowTs } from '../../lib/time';
  import { haptic, on } from '../../lib/tg';
  import { shrink } from '../../lib/photo';
  import { fmtPhone } from '../../lib/phone';
  import Sheet from '../../ui/Sheet.svelte';
  import Wallet from '@lucide/svelte/icons/wallet';
  import Button from '../../ui/Button.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Notice from '../../ui/Notice.svelte';
  import { burst } from '../../ui/burst';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  const e = $derived(eventById(id));
  let detail = $state<EventFull | null>(null);
  // always fresh, never the prefetched copy: the treasurer's name and phone come only with the seat held, and a copy
  // taken as the finger touched "Go" was asked before the hold
  $effect(() => { api.event(id).then((x) => (detail = x)).catch(() => {}); });
  const until = $derived(e?.my?.holdUntil ?? null);
  const doubt = $derived(e?.my?.status === 'going' ? (e.my.receiptFlags ?? []) : []);
  const phone = $derived(fmtPhone(detail?.payPhone ?? ''));

  const copy = () => copyText(phone, t('pay.copied')); // the number is selectable too

  let busy = $state(false);
  let picker = $state<HTMLInputElement>();
  function paid() {
    haptic.ok(); burst(false, undefined, e?.emoji); say(t('pay.done'), 'party_popper_3d'); // the ticket: a moment
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
      say(x instanceof ApiErr && x.code === 'closed' ? t('pay.expired') : x instanceof ApiErr && x.code === 'rate_limited' ? t('pay.tooMany') : x instanceof ApiErr && x.message === 'not_receipt' ? t('pay.notReceipt') : x instanceof ApiErr && x.code === 'bad_input' ? t('ed.photoBad') : t('common.error'), 'warning_3d');
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

<Sheet {overlay} icon={Wallet} title={doubt.length ? t('pay.doubtTitle') : t('pay.title')}>
  {#if e && doubt.length}
    <div class="page">
      <p class="fs-body dim lead">{t('pay.doubtLead')}</p>
      {#each doubt as f (f)}<Notice tone="warning" text={f === 'recipient_mismatch' ? t('pay.flagTo', { name: detail?.payToName ?? '…' })
        : t(`rc.flag.${f}` as 'rc.flag.duplicate')} />{/each}
      <p class="fs-sub faint note">{t('pay.doubtNote')}</p>
    </div>
  {:else if e}
    <div class="page">
      <div class="lead">
        <h2 class="fs-t1 num">{money(e.price ?? 0)}</h2>
        <p class="fs-sub dim ellipsis">{e.title}</p>
        <p class="fs-body dim txt">{t('pay.lead', { price: money(e.price ?? 0) })}</p>
      </div>
      <!-- the name and the number stay selectable: a copy by hand works when the clipboard doesn't -->
      <div class="selectable">
        <Group>
          <Row dense title={detail?.payToName ?? '…'} subtitle={t('pay.to')} />
          {#if phone}
            <Row dense title={phone} subtitle={t('pay.phone')}>{#snippet trailing()}<IconButton icon={Copy} kind="tinted" size="s" label={t('pay.copy')} onclick={copy} />{/snippet}</Row>
          {:else}
            <Row dense title="…" subtitle={t('pay.phone')} />
          {/if}
        </Group>
      </div>
      {#if until}<Notice tone={until < nowTs() ? 'danger' : 'warning'} text={until < nowTs() ? t('pay.expired') : t('pay.until', { time: time(until) })} />{/if}
      <Notice tone="accent" icon={TelegramMark} text={t('pay.bot')} />
      <p class="fs-sub faint note">{t('pay.note')}</p>
      <div class="rel"><Button kind="plain" size="m" onclick={release}>{t('pay.release')}</Button></div>
    </div>
  {/if}

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={() => picker?.click()}>{#snippet icon()}<ReceiptIcon size={18} />{/snippet}{doubt.length ? t('pay.another') : t('pay.upload')}</Button>
    {#if doubt.length}<div class="rel"><Button kind="plain" size="m" onclick={keep}>{t('pay.keep')}</Button></div>{/if}
    <input type="file" accept="image/*,application/pdf" hidden bind:this={picker} onchange={upload} />
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-3); }
  .lead { padding: 0 var(--s-1); }
  .lead .txt { margin-top: var(--s-3); }
  .note { padding: 0 var(--s-4); }
  .rel { display: flex; justify-content: center; margin-top: var(--s-1); --plain-ink: var(--text-2); }
</style>
