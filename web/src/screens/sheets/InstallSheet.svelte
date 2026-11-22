<script lang="ts">
  // The home-screen app, offered once per phone inside Telegram (App installHint): what it is, the icon landing on a
  // home screen's row, and "Add", which opens /install in the phone's browser (Safari or Chrome hold "Add to Home
  // Screen"; Telegram's own browser does not). For its first 5 s it can't be closed (Back, the scrim and a pull spring
  // back: Sheet `hold`), so it is read first: the ring by "Not now" fills meanwhile (the owner's ask, Nov 22).
  import { onMount } from 'svelte';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { once } from '../../lib/greet';
  import { openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Smartphone from '@lucide/svelte/icons/smartphone';

  let { overlay }: { overlay: Overlay } = $props();
  const WAIT = 5;
  let left = $state(WAIT), started = $state(false);

  onMount(() => {
    once('kb-install'); // shown: never again on this phone, however it ends
    // the ring's first frame is empty, then each second glides into the next (a step per second under reduced motion)
    const first = requestAnimationFrame(() => (started = true));
    const tick = setInterval(() => { if (--left <= 0) clearInterval(tick); }, 1000);
    return () => { cancelAnimationFrame(first); clearInterval(tick); };
  });

  function add() {
    openLink(location.origin + '/install', true);
    close(overlay.id);
  }
</script>

{#snippet ring()}
  <svg class={['ring', { started }]} viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
    <circle cx="10" cy="10" r="8" /><circle class="go" cx="10" cy="10" r="8" pathLength="1" stroke-dashoffset={started ? (left - 1) / WAIT : 1} />
  </svg>
{/snippet}

<Sheet {overlay} icon={Smartphone} title={t('inst.title')} hold={() => left > 0}>
  <div class="inst">
    <div class="home" aria-hidden="true">
      <i></i>
      <span class="app"><img src="/favicon.svg" alt="" width="56" height="56" /><b>KBTU</b></span>
      <i></i>
    </div>
    <h2 class="t-h2">{t('inst.title')}</h2>
    <p class="t-callout">{t('inst.text')}</p>
  </div>
  {#snippet footer()}
    <div class="acts">
      <Button size="l" full lit onclick={add}>{t('inst.add')}</Button>
      <Button kind="plain" full disabled={left > 0} icon={left > 0 ? ring : undefined} onclick={() => close(overlay.id)}>{t('inst.later')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .inst { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-1) var(--s-1) var(--s-2); text-align: center; }
  .inst p { color: var(--text-2); text-wrap: pretty; }
  /* a home screen's row: two quiet places and ours between them, which lands once the sheet stands */
  .home { display: flex; align-items: flex-start; gap: var(--s-5); margin-bottom: var(--s-2); padding: var(--s-5) var(--s-5) var(--s-3); border-radius: var(--r-xl); background: var(--surface); box-shadow: inset 0 0 0 0.5px var(--line-2); }
  .home i { width: 56px; height: 56px; border-radius: var(--r-m); background: var(--fill); }
  .app { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); animation: land 720ms var(--ease-spring) 420ms backwards; }
  .app img { display: block; border-radius: var(--r-m); box-shadow: var(--lg-lift); }
  .app b { font: 500 var(--fs-micro)/1 var(--font-text); color: var(--text-2); }
  @keyframes land { from { opacity: 0; transform: translate3d(0, -18px, 0) scale(1.18); } }
  .acts { display: flex; flex-direction: column; gap: var(--s-1); }
  /* the wait: a hairline ring that closes over 5 s. An 18 px stroke, the one thing here that isn't transform or opacity */
  .ring { transform: rotate(-90deg); fill: none; stroke: var(--fill-2); stroke-width: 2; }
  .ring .go { stroke: currentColor; stroke-linecap: round; stroke-dasharray: 1; }
  .ring.started .go { transition: stroke-dashoffset 1s linear; }
  @media (prefers-reduced-motion: reduce) {
    .app { animation: none; }
    .ring.started .go { transition: none; }
  }
</style>
