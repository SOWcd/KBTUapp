<script lang="ts">
  // My QR — the back of my badge. Opens over a blurred scrim like the ticket, follows the phone's tilt and
  // leans toward a pressing finger. The code holds only a link into the app (my profile; the friend invite
  // takes its place once friends exist, SPEC §4.7), in the brand gradient with the app's mark in the middle
  // (the face is once, on top; owner, Oct 4) — big enough for any phone camera across a table. Back, a tap
  // outside or Close dismisses it.
  import { onMount } from 'svelte';
  import type { PersonCard } from '../../lib/api';
  import { hero, QR_TONE, lookOf, STRAP, banded } from '../../lib/awards';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { glass } from '../../ui/glass';
  import Qr from '../../ui/Qr.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Founder from '../../ui/Founder.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import LanyardHolo from '../../ui/LanyardHolo.svelte';
  import QrCode from '@lucide/svelte/icons/qr-code';

  let { overlay, link, p }: { overlay: Overlay; link: string; p: PersonCard } = $props();
  const h = $derived(hero(p));
  // the back of the badge I wear: the same skin, its strap and clip on top (it stayed in the old blue)
  const sower = $derived(p.skin === 'sower');
  const look = $derived(lookOf(p)); // the class and the strap's word
  // the capsule's title (SPEC §8.2), with a QR mark, and dark like the scrim under it: in the light look it was dark
  // text on a darkened glass
  $effect(() => { overlay.title = t('me.qr'); overlay.icon = QrCode; overlay.theme = 'dark'; });

  let wrap: HTMLDivElement;
  let scrim: HTMLDivElement;
  let pass = $state<HTMLDivElement>();
  let gone = false;

  onMount(() => {
    haptic.soft();
    wrap.animate([{ opacity: 0, transform: 'translate3d(0,70px,0) scale(0.92)' }, { opacity: 1, transform: 'none' }],
      { duration: 480, easing: 'cubic-bezier(.2,.9,.25,1.1)' });
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: 'ease-out' });
    return hideChrome();
  });

  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translate3d(0,60px,0) scale(0.94)' }],
      { duration: 240, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    const a = scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });

  // the pass leans toward the finger (≤ 5°) and gives a little; it springs back on release (as the ticket)
  function press(ev: PointerEvent) {
    if (!pass) return;
    const r = pass.getBoundingClientRect();
    pass.style.setProperty('--px', (((ev.clientX - r.left) / r.width) * 2 - 1).toFixed(2));
    pass.style.setProperty('--py', (((ev.clientY - r.top) / r.height) * 2 - 1).toFixed(2));
    pass.style.setProperty('--ps', '0.985');
  }
  function release() {
    if (!pass) return;
    for (const v of ['--px', '--py']) pass.style.setProperty(v, '0');
    pass.style.setProperty('--ps', '1');
  }
</script>

<div class="scrim" bind:this={scrim} onclick={() => close(overlay.id)} role="presentation"></div>
<div class="wrap" bind:this={wrap}>
  <div class="stage {look}">
    <div class="strap" aria-hidden="true"><span>{STRAP[look]}</span></div>
    <div class="clip" aria-hidden="true"></div>
    <div class="pass" class:banded={banded(look)} bind:this={pass} use:glass role="group" aria-label={t('me.qr')}
         onpointerdown={press} onpointerup={release} onpointercancel={release} onpointerleave={release}>
      {#if banded(look)}<LanyardBand {look} />{/if}
      <span class="slot" aria-hidden="true"></span>
      <div class="who">
        <span class="ph"><Avatar person={h.person} size={46} tappable={false} /></span>
        <span class="tx">
          <b class="nm">{h.name}{#if h.status}<Founder size={17} />{/if}</b>
          <span class="role">{h.title}</span>
        </span>
      </div>
      <div class="plate">
        <Qr text={link} tone={sower ? undefined : QR_TONE}><span class="appmark"><KbtuMark /></span></Qr>
      </div>
      <span class="foot"><LanyardHolo {look} no={h.no} /></span>
    </div>
  </div>
  <p class="hint">{t('me.qrHint')}</p>
  <button class="pill glass glass-pill" use:glass onclick={() => close(overlay.id)}>{t('common.close')}</button>
</div>

<style>
  .scrim {
    --dim: rgba(3, 4, 10, 0.8);
    position: absolute; inset: 0; z-index: var(--z-sheet);
    background: radial-gradient(70% 45% at 50% 42%, rgba(59, 107, 255, 0.36), transparent 72%), var(--dim);
    -webkit-backdrop-filter: blur(18px) saturate(120%); backdrop-filter: blur(18px) saturate(120%);
  }
  :global(html.lowfx) .scrim { --dim: rgba(3, 4, 10, 0.92); -webkit-backdrop-filter: none; backdrop-filter: none; }
  .wrap {
    position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
    padding: calc(var(--top) + 8px) 20px calc(var(--safe-bottom) + 16px);
  }
  .wrap > :global(*) { pointer-events: auto; }
  .stage { perspective: 900px; display: flex; flex-direction: column; align-items: center; }
  /* the strap and clip as on the badge (Hero.svelte) */
  .strap { width: 26px; height: 40px; display: flex; justify-content: center; align-items: center; padding-bottom: 4px; overflow: hidden;
    background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25); }
  .strap span { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 7.5px/26px var(--font-text); letter-spacing: 0.22em; color: rgba(255, 255, 255, 0.8); white-space: nowrap; }
  .clip { position: relative; z-index: 2; width: 36px; height: 15px; margin-bottom: -9px; border-radius: 5px;
    background: linear-gradient(180deg, #F4F6FB, #9AA4B8); box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4), inset 0 1px 0 #fff; }

  /* the badge's own material, seen from the back */
  .pass {
    position: relative; overflow: hidden; width: min(330px, calc(100vw - 40px), calc(100dvh - 420px)); padding: 26px 0 16px; /* a band makes it taller: a short phone narrows it (the QR stays ~180 px) */ border-radius: 26px; color: #fff;
    background: radial-gradient(110% 70% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(160deg, #2A4FD6, #121A3D 70%);
    box-shadow: 0 34px 60px -22px rgba(0, 0, 0, 0.75), 0 10px 24px -12px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.28);
    transform: rotateX(calc(var(--gy, 0) * -7deg + var(--py, 0) * 5deg)) rotateY(calc(var(--gx, 0) * 9deg - var(--px, 0) * 5deg)) scale(var(--ps, 1));
    transition: transform 160ms ease-out;
    touch-action: manipulation;
  }
  .pass::after { content: ''; position: absolute; inset: 0; pointer-events: none; background: linear-gradient(115deg, transparent 32%, rgba(255, 255, 255, 0.12) 46%, transparent 60%);
    background-size: 260% 100%; background-position: calc(50% + var(--gx, 0) * 45%) 0; }
  .slot { position: absolute; z-index: 1; top: 9px; left: 50%; width: 46px; height: 8px; margin-left: -23px; border-radius: 4px;
    background: rgba(5, 8, 20, 0.55); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7), 0 1px 0 rgba(255, 255, 255, 0.16); }

  .who { position: relative; display: flex; align-items: center; gap: 12px; margin: 0 18px; }
  .banded { padding-top: 0; } /* the art band on top (LanyardBand) */
  .banded .who { margin-top: 14px; }
  .foot { display: block; margin: 14px 18px 0; }
  .ph { flex: none; padding: 2px; border-radius: 15px; background: rgba(255, 255, 255, 0.16); }
  .banded .ph, .studex .ph, .sower .ph { background: #fff; }
  .ph :global(.av), .ph :global(.av img), .ph :global(.ini) { border-radius: 13px; }
  .tx { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .nm { display: flex; align-items: center; gap: 6px; font: 780 19px/1.15 var(--font-display); letter-spacing: -0.02em; }
  .role { font: 760 10.5px/1.25 var(--font-text); letter-spacing: 0.13em; text-transform: uppercase; color: var(--role, #A9C0FF); }

  .plate { position: relative; margin: 14px 18px 0; padding: 16px; border-radius: 22px; background: #fff;
    box-shadow: 0 16px 30px -18px rgba(0, 0, 0, 0.6), inset 0 0 0 1px rgba(10, 15, 36, 0.05); }

  /* each look's body and strap below its band (LanyardBand), as on the badge (Hero.svelte) */
  .cheer { --role: #FFC83D; }
  .cheer .pass { background: linear-gradient(180deg, #1D2042, #0A0B17); }
  .cheer .strap { background: linear-gradient(90deg, #1E2140, #3A3F72 50%, #1E2140); }
  .cheer .strap span { color: #FFC83D; }
  .knights { --role: #9CC2FF; }
  .knights .pass { background: linear-gradient(180deg, #0F2B66, #071631); }
  .knights .strap { background: linear-gradient(90deg, #163E7C, #2F6BD0 50%, #163E7C); }
  .knights .strap span { letter-spacing: 0.12em; } /* seven letters on the short strap */
  .studex { --role: rgba(255, 255, 255, 0.92); }
  .studex .pass { background: linear-gradient(104deg, #DE3B2E, #C12E22 29%, #fff 29%, #fff 30.6%, #1D3B7A 30.6%, #0F2350); }
  .studex .strap { background: linear-gradient(90deg, #A9271E, #CF3428 50%, #A9271E); }
  .sower { --role: rgba(255, 255, 255, 0.92); }
  .sower .pass { background: radial-gradient(90% 120% at 0% 0%, #26262B, #000 62%); }
  .sower .pass::before { content: ''; position: absolute; right: -130px; top: -130px; width: 340px; height: 340px; border-radius: 50%; pointer-events: none;
    background: repeating-radial-gradient(circle, transparent 0 18px, rgba(255, 255, 255, 0.12) 18px 19.5px); }
  .sower .strap { background: linear-gradient(90deg, #DCDCE0, #fff 50%, #DCDCE0); }
  .sower .strap span { color: #000; }
  .sower .plate :global(.appmark) { background: #0A0A0A; }

  .hint { max-width: 300px; text-align: center; font: 550 13px/1.35 var(--font-text); color: rgba(255, 255, 255, 0.66); }
  .pill { position: relative; height: 44px; padding: 0 24px; border-radius: var(--r-full); color: #fff; font: 650 15px/1 var(--font-text); background-color: rgba(255, 255, 255, 0.1); }
  .pill:active { transform: scale(0.96); }
</style>
