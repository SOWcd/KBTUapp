<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import { api, type DonationReview } from '../../lib/api';
  import { data, loadDonations, loadSupport } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { whenLine } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Button from '../../ui/Button.svelte';
  import Notice from '../../ui/Notice.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const rows = $derived(data.donations);
  let failed = $state(false);
  let selected = $state<DonationReview | null>(null);
  let amount = $state('');
  let busy = $state(false);
  let image = $state('');
  let imageFailed = $state(false);
  const owner = $derived(session.me?.role === 'admin' && !!session.me.founder);
  const validAmount = $derived(/^\d+$/.test(amount) && +amount > 0 && +amount <= 100000000);
  $effect(() => { if (!owner) { data.donations = null; selected = null; close(overlay.id); } });
  let alive = true;
  onDestroy(() => { alive = false; });
  async function load() {
    failed = false;
    const ok = await loadDonations();
    if (alive && owner) failed = !ok;
  }
  onMount(() => { void load(); });
  function pick(row: DonationReview) {
    selected = selected?.id === row.id ? null : row;
    amount = String(row.amount ?? row.readAmount ?? '');
    haptic.tap();
  }
  $effect(() => {
    const id = selected?.id, hasImage = selected?.image;
    image = ''; imageFailed = false;
    let live = true, url = '';
    if (id && hasImage && owner) void api.donationImage(id).then((src) => {
      url = src;
      if (live) image = src; else URL.revokeObjectURL(src);
    }, () => { if (live) imageFailed = true; });
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  });
  async function decide(action: 'confirm' | 'reject' | 'undo') {
    const row = selected;
    if (!row || busy || (action === 'confirm' && !validAmount)) return;
    if (action === 'reject' && !(await sheets.ask({ title: t('sp.rejectAsk'), text: t('sp.rejectText'), ok: t('rc.reject'), cancel: t('common.cancel'), danger: true }))) return;
    if (action === 'confirm' && row.status === 'confirmed' && row.amount !== +amount
      && !(await sheets.ask({ title: t('sp.correctAsk'), text: t('sp.correctText', { amount: money(+amount) }), ok: t('sp.confirm'), cancel: t('common.cancel') }))) return;
    busy = true; haptic.tap();
    try {
      await api.reviewDonation(row.id, row.revision, action, action === 'confirm' ? +amount : undefined);
      selected = null;
      await load(); void loadSupport();
      haptic.ok();
    } catch { say(t('common.error'), 'warning_3d'); await load(); selected = null; }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} full title={t('sp.queue')} icon={HandHeart}>
  <p class="fs-sub dim">{t('sp.reviewHint')}</p>
  {#if failed}<Button kind="secondary" onclick={load}>{t('common.retry')}</Button>{/if}
  {#if rows}
    {#if !rows.length}<p class="fs-body dim">{t('sp.queueEmpty')}</p>{/if}
    <Group>
      {#each rows as row (row.id)}
        <Row title={row.name} subtitle={`${t(`sp.${row.status}`)} · ${whenLine(row.at)}`} value={row.amount || row.readAmount ? money(row.amount ?? row.readAmount!) : undefined}
          accessory="disclosure" open={selected?.id === row.id} disabled={busy} onclick={() => pick(row)} />
        {#if selected?.id === row.id}
          <div class="review">
            {#each row.flags as flag (flag)}<Notice tone="neutral" text={flag === 'too_early' ? t('sp.old') : flag === 'ocr_unavailable' || flag === 'unreadable' ? t('sp.partial') : t(`rc.flag.${flag}` as 'rc.flag.duplicate', { name: row.recipient ?? '' })} />{/each}
            {#if row.auto}<p class="fs-sub dim">{t('rc.auto')}</p>{/if}
            {#if row.recipient}<Row title={t('rc.recipient')} value={row.recipient} />{/if}
            {#if row.sender}<Row title={t('rc.sender')} value={row.sender} />{/if}
            {#if row.no}<Row title={t('rc.no')} value={row.no} />{/if}
            {#if row.paidAt}<Row title={t('rc.paidAt')} value={whenLine(row.paidAt)} />{/if}
            {#if image}<img class="receipt" src={image} alt={t('rc.title')} />{:else if imageFailed}<p class="fs-sub dim">{t('common.error')}</p>{/if}
            {#if row.image}
              <label class="amount"><span class="fs-sub dim">{t('rc.amount')}</span><input inputmode="numeric" autocomplete="off" bind:value={amount} aria-label={t('rc.amount')} /></label>
              <div class="actions">
                <Button kind="secondary" full loading={busy} disabled={!validAmount} onclick={() => decide('confirm')}>{t('sp.confirm')}</Button>
                <Button kind="destructive" full disabled={busy} onclick={() => decide('reject')}>{t('rc.reject')}</Button>
              </div>
            {/if}
            {#if row.undo}<Button kind="secondary" disabled={busy} onclick={() => decide('undo')}>{t('adm.undo')}</Button>{/if}
          </div>
        {/if}
      {/each}
    </Group>
  {/if}
</Sheet>

<style>
  .review { display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-4); }
  .receipt { display: block; width: 100%; height: auto; border-radius: var(--r-m); }
  .amount { display: flex; flex-direction: column; gap: var(--s-2); }
  .amount input { min-width: 0; width: 100%; padding: var(--s-3); border-radius: var(--r-m); background: var(--fill); color: var(--text); font: inherit; }
  .actions { display: flex; gap: var(--s-2); }
</style>
