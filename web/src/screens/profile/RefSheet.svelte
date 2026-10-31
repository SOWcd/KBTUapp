<script lang="ts">
  // My invite link (referrals) as a QR to show across a table (owner, Oct 31), or sent as our bot's card. The same
  // link either way: my badge's code in it, never my ID.
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, shareCard } from '../../lib/tg';
  import { QR_TONE } from '../../lib/awards';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Qr from '../../ui/Qr.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';

  let { overlay, code }: { overlay: Overlay; code: string } = $props();
  const link = $derived(`https://t.me/KBTUappBot?startapp=r_${code}`);
  let busy = $state(false);
  async function send() {
    haptic.tap(); busy = true;
    try { await shareCard({ kind: 'rf', id: '0' }, link, t('ref.text'), () => (busy = false)); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('ref.title')}>
  <h2 class="t-h2 hd">{t('ref.title')}</h2>
  <div class="pass">
    <div class="plate"><span class="code"><Qr text={link} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></span></div>
    <p class="cap">{t('ref.qr')}</p>
  </div>
  <div class="acts">
    <Button kind="primary" size="l" full loading={busy} onclick={send}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('fr.send')}</Button>
  </div>
</Sheet>

<style>
  .hd { margin: 4px 0 14px; }
  /* the badge's material, as on AddFriend */
  .pass { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 18px 18px 16px; border-radius: var(--r-xl); color: rgb(255, 255, 255);
    background: radial-gradient(110% 70% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(160deg, rgb(42, 79, 214), rgb(18, 26, 61) 70%);
    box-shadow: 0 26px 46px -26px rgba(18, 26, 61, 0.9), inset 0 1px 0 rgba(255, 255, 255, 0.25); }
  .plate { width: 220px; height: 220px; padding: 12px; border-radius: var(--r-l); background: rgb(255, 255, 255); display: flex; align-items: center; justify-content: center;
    box-shadow: 0 16px 30px -18px rgba(0, 0, 0, 0.6); }
  .code { display: block; width: 100%; }
  .cap { margin-top: 8px; font: 650 var(--fs-body)/1.3 var(--font-text); text-align: center; text-wrap: balance; }
  .acts { margin-top: 12px; }
</style>
