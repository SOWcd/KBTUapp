<script lang="ts">
  // The home-screen app, offered once per phone inside Telegram (App installHint): what it is, a phone playing the
  // owner's own recording of it (a tap on the icon, the splash, the Afisha: a real app, not a shortcut into Telegram;
  // muted, looped, resting on the Afisha; the files come with this lazy sheet, never with the app), and "Add", which
  // opens /install in the phone's browser (Safari or Chrome hold "Add to Home Screen"; Telegram's own browser does
  // not). For its first 5 s it can't be closed (Back, the scrim and a pull spring
  // back: Sheet `hold`), so it is read first: the ring by "Not now" fills meanwhile (the owner's ask, Nov 22).
  import { onMount } from 'svelte';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { once } from '../../lib/greet';
  import { openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Smartphone from '@lucide/svelte/icons/smartphone';
  import clip from '../../assets/install/open.mp4';
  import poster from '../../assets/install/open.webp';

  let { overlay }: { overlay: Overlay } = $props();
  const WAIT = 5;
  let left = $state(WAIT), started = $state(false);
  // reduced motion: the poster (the home screen with our icon) stands still
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let video: HTMLVideoElement;

  onMount(() => {
    once('kb-install'); // shown: never again on this phone, however it ends
    // the ring's first frame is empty, then each second glides into the next (a step per second under reduced motion)
    const first = requestAnimationFrame(() => (started = true));
    // iOS plays inline without a tap only when muted is a property, not just the attribute; refused (Low Power Mode): the poster stays
    if (!still) { video.muted = true; video.play().catch(() => {}); }
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
    <div class="phone" aria-hidden="true">
      <video bind:this={video} src={clip} {poster} width="440" height="952" muted playsinline loop autoplay={!still} preload="auto" disablepictureinpicture disableremoteplayback></video>
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
  /* a phone: a black bezel around the recording, the screen's corners a real iPhone's share of its width */
  .phone { width: 148px; margin: var(--s-2) 0 var(--s-3); padding: 5px; border-radius: var(--r-xl); background: black; box-shadow: 0 0 0 0.5px var(--line-2), var(--lg-lift), 0 28px 44px -28px rgba(0, 0, 0, 0.55); animation: rise 620ms var(--ease-spring) 180ms backwards; }
  .phone video { display: block; width: 100%; height: auto; aspect-ratio: 440 / 952; border-radius: var(--r-l); background: black; object-fit: cover; pointer-events: none; }
  /* a short screen: a smaller phone, so the words under it still show without a scroll */
  @media (max-height: 700px) { .phone { width: 112px; padding: 4px; border-radius: var(--r-l); } .phone video { border-radius: var(--r-m); } }
  @media (max-height: 600px) { .phone { width: 92px; margin: 0 0 var(--s-1); } }
  @keyframes rise { from { opacity: 0; transform: translate3d(0, 14px, 0) scale(0.96); } }
  .acts { display: flex; flex-direction: column; gap: var(--s-1); }
  /* the wait: a hairline ring that closes over 5 s. An 18 px stroke, the one thing here that isn't transform or opacity */
  .ring { transform: rotate(-90deg); fill: none; stroke: var(--fill-2); stroke-width: 2; }
  .ring .go { stroke: currentColor; stroke-linecap: round; stroke-dasharray: 1; }
  .ring.started .go { transition: stroke-dashoffset 1s linear; }
  @media (prefers-reduced-motion: reduce) {
    .phone { animation: none; }
    .ring.started .go { transition: none; }
  }
</style>
