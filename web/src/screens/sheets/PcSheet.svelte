<script lang="ts">
  // On a computer (Telegram Desktop, the web clients, a desktop browser): the app is made for phones, so it says so once
  // with a code to open it on the phone, and "I understand, continue on the computer" lets them in (owner, Oct 13: warn,
  // never forbid). Closed any other way, it asks again next time.
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { QR_TONE } from '../../lib/awards';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import Qr from '../../ui/Qr.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  let { overlay, ok }: { overlay: Overlay; ok: () => void } = $props();
</script>

<Sheet {overlay} title={t('pc.title')}>
  <div class="pc">
    <Emoji name="laptop_3d" size={56} />
    <h2 class="t-h2">{t('pc.title')}</h2>
    <p class="t-callout">{t('pc.text')}</p>
    <div class="qr"><Qr text="https://t.me/KBTUappBot?startapp" tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></div>
    <p class="t-foot">{t('pc.scan')}</p>
  </div>
  {#snippet footer()}
    <Button kind="secondary" size="l" full onclick={() => { ok(); close(overlay.id); }}>{t('pc.continue')}</Button>
  {/snippet}
</Sheet>

<style>
  .pc { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 4px 4px 8px; text-align: center; }
  .pc p { text-wrap: pretty; }
  .qr { width: 168px; height: 168px; margin: 6px 0 2px; padding: 10px; border-radius: 20px; background: #fff; }
</style>
