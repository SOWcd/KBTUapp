<script lang="ts">
  import { onMount } from 'svelte';
  import { api, ApiErr } from '../../lib/api';
  import { data, loadSupport, supportWrite } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say } from '../../lib/state/ui.svelte';
  import { t, money, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, on } from '../../lib/tg';
  import { shrink } from '../../lib/photo';
  import { sponsorMedal, tierLabel } from '../../lib/awards';
  import { dayMonth } from '../../lib/time';
  import Medal from '../../ui/Medal.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  const mine = $derived(data.support);
  let busy = $state(false);
  let picker = $state<HTMLInputElement>();
  let choosing = $state(false);
  let switchKey = $state(0);
  const RECEIPT_CONSENT = 'dn1', PUBLIC_CONSENT = 'sp1';
  const policy = () => ({ label: t('set.policy'), url: `${location.origin}/privacy?lang=${i18n.lang}` });

  onMount(() => {
    void loadSupport();
    const refresh = () => { if (!document.hidden) void loadSupport(); };
    document.addEventListener('visibilitychange', refresh);
    const off = on('activated', refresh);
    return () => { document.removeEventListener('visibilitychange', refresh); off(); };
  });

  async function attach() {
    if (busy || choosing) return;
    choosing = true;
    const agreed = await sheets.ask({ title: t('sp.attach'), text: t('sp.receiptConsent'), ok: t('sp.choose'), cancel: t('common.cancel'), link: policy() });
    choosing = false;
    if (agreed) picker?.click();
  }
  async function upload(e: Event) {
    const input = e.currentTarget as HTMLInputElement, file = input.files?.[0];
    input.value = '';
    if (!file || busy) return;
    if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'warning_3d'); return; }
    busy = true; supportWrite(true); haptic.tap();
    try {
      data.support = await api.donationReceipt(await shrink(file, 2400), RECEIPT_CONSENT);
      haptic.ok();
      say(t(data.support.receipts[0]?.status === 'confirmed' ? 'don.thanks' : 'sp.sent'), 'blue_heart_3d');
    } catch (error) {
      haptic.error();
      say(t(error instanceof ApiErr && error.code === 'rate_limited' ? 'sp.limit' : error instanceof ApiErr && error.code === 'bad_input' ? 'ed.photoBad' : 'common.error'), 'warning_3d');
    } finally { busy = false; supportWrite(false); }
  }
  async function publish(show: boolean) {
    if (!mine || busy || choosing) return;
    const rev = mine.rev;
    choosing = true;
    const agreed = !show || await sheets.ask({ title: t('sp.public'), text: t('sp.publicConsent'), ok: t('sp.publish'), cancel: t('common.cancel'), link: policy() });
    choosing = false;
    if (!agreed) { switchKey++; return; }
    const was = mine.show;
    mine.show = show; busy = true; supportWrite(true); haptic.tap();
    data.sponsors = null;
    try { data.support = await api.sponsorConsent(show, PUBLIC_CONSENT, rev); }
    catch { if (data.support) data.support.show = was; switchKey++; say(t('common.error'), 'warning_3d'); }
    finally { busy = false; supportWrite(false); }
  }
</script>

<div class="support">
  {#if mine}
    {#if mine.tier}
      <div class="earned">
        <Medal a={sponsorMedal(mine.tier)} size={96} />
        <div><h2 class="t-h2">{t('ach.sponsor.name')} · {tierLabel(mine.tier, 3)}</h2>
          <p class="fs-body">{t('sp.total', { amount: money(mine.total) })}</p><p class="fs-sub dim">{t('sp.private')}</p></div>
      </div>
    {:else}<p class="fs-body">{t('sp.total', { amount: money(mine.total) })}</p>{/if}
    <p class="fs-sub dim">{t('sp.tiers', { second: money(mine.thresholds[1]), third: money(mine.thresholds[2]), rate: money(mine.starRate) })}</p>
  {/if}
  {#if session.donate}
    <Button kind="secondary" full loading={busy} disabled={choosing || mine?.receiptConsent !== RECEIPT_CONSENT} onclick={attach}>{t('sp.attach')}</Button>
    <input hidden type="file" accept="image/*,application/pdf" bind:this={picker} onchange={upload} />
    <p class="fs-sub faint">{t('sp.receiptHint')}</p>
  {/if}
  {#if mine?.receipts.length}
    <Group caption={t('sp.receipts')}>
      {#each mine.receipts as r (r.id)}
        <Row title={t(`sp.${r.status}`)} subtitle={dayMonth(r.at)} value={r.amount ? money(r.amount) : undefined} />
      {/each}
    </Group>
  {/if}
  {#if mine && (mine.tier || mine.show)}
    {#key switchKey}<Group footnote={t('sp.publicHint')}>
      <Row title={t('sp.public')} accessory="switch" checked={mine.show} disabled={busy || choosing || (!mine.show && mine.version !== PUBLIC_CONSENT)} onchange={publish} />
    </Group>{/key}
  {/if}
  <Group caption={t('sp.sponsors')} footnote={t('sp.listHint')}>
    {#if data.sponsors?.length}
      {#each data.sponsors as p, i (i)}<Row title={p.name} value={tierLabel(p.tier, 3)} />{/each}
    {:else if data.sponsors}<Row title={t('sp.empty')} />{/if}
  </Group>
</div>

<style>
  .support { display: flex; flex-direction: column; gap: var(--s-3); width: 100%; text-align: start; }
  .earned { display: flex; align-items: center; gap: var(--s-5); padding-block: var(--s-4) var(--s-6); }
  .earned > div { min-width: 0; }
  .earned p { margin-top: var(--s-2); }
</style>
