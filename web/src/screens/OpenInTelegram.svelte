<script lang="ts">
  // Outside Telegram (a plain browser, not /show): the app signs in through Telegram, so it says where it lives, with the
  // button that opens it there and, on a computer, the same link as a code for the phone; "continue in the browser" still
  // lets them in (owner, Oct 13: warn, never forbid; Oct 30: "open in Telegram").
  import Button from '../ui/Button.svelte';
  import KbtuMark from '../ui/KbtuMark.svelte';
  import Qr from '../ui/Qr.svelte';
  import { QR_TONE } from '../lib/awards';
  import { t } from '../lib/i18n/index.svelte';

  let { link, oncontinue }: { link: string; oncontinue: () => void } = $props();
  const phone = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
</script>

<main class="tgo scroll">
  <span class="mark appmark"><KbtuMark /></span>
  <h1 class="t-h1">{t('tgo.title')}</h1>
  {#if !phone}
    <div class="qr"><Qr text={link} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></div>
    <p class="t-foot">{t('pc.scan')}</p>
  {/if}
  <div class="acts">
    <Button kind="primary" size="l" full onclick={() => (location.href = link)}>{t('tgo.open')}</Button>
    <Button kind="plain" size="m" onclick={oncontinue}>{t('tgo.browser')}</Button>
  </div>
</main>

<style>
  .tgo { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-4);
    padding: calc(var(--safe-top) + var(--s-8)) var(--gutter) calc(var(--safe-bottom) + var(--s-6)); text-align: center; }
  .mark { width: 76px; height: 76px; flex: none; box-shadow: none; } /* the QR's white ring isn't for a page */
  h1 { max-width: 320px; text-wrap: balance; }
  .qr { width: 176px; height: 176px; flex: none; margin-top: var(--s-2); padding: 10px; border-radius: var(--r-l); background: white; }
  .acts { width: min(100%, 360px); display: flex; flex-direction: column; align-items: center; gap: var(--s-2); margin-top: var(--s-4); }
</style>
