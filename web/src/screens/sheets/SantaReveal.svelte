<script lang="ts">
  // Secret Santa's moment (it should feel like a game): the sealed card lifts off the event's page to
  // the middle of a dark screen, turns over once and shows whom I give to, large; their wishlist rises under it.
  // Transform and opacity only. Reduced motion and power saving: the open card fades in, nothing moves.
  import { onMount } from 'svelte';
  import Gift from '@lucide/svelte/icons/gift';
  import type { PersonRef } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import SantaBack from './SantaBack.svelte';

  let { overlay, to, from }: { overlay: Overlay; to: { person: PersonRef; wish: string }; from: DOMRect | null } = $props();
  $effect(() => { overlay.title = t('santa.title'); overlay.icon = Gift; });

  const W = Math.min(248, Math.round(innerWidth * 0.66));
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('lowfx') || !Element.prototype.animate;
  const EASE = 'cubic-bezier(.2,.9,.25,1)';
  const FLY = 420, TURN = 720, SPIN = 820, SHOWN = TURN + SPIN * 0.62; // the flight; the turn starts; it lasts; the face is towards me
  const SPARKS = Array.from({ length: 8 }, (_, i) => { const a = (i / 8) * Math.PI * 2 + 0.4, r = W * (0.74 + (i % 3) * 0.1); return { x: Math.cos(a) * r, y: Math.sin(a) * r * 1.2, s: 0.6 + (i % 4) * 0.25 }; });

  let scrim: HTMLDivElement, wrap: HTMLDivElement, stage: HTMLDivElement, card: HTMLDivElement, glow: HTMLSpanElement;
  let shown = $state(still); // the face is out: the scrim's tap may close
  let gone = false;
  onMount(() => {
    const off = hideChrome();
    haptic.soft();
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: still ? 200 : 320, easing: 'ease-out' });
    if (still) {
      wrap.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: 'ease-out' });
      haptic.ok();
      return off;
    }
    // the flight: from where the small card lay on the page
    const r = stage.getBoundingClientRect();
    const f = from ? { x: from.left + from.width / 2 - (r.left + r.width / 2), y: from.top + from.height / 2 - (r.top + r.height / 2), s: from.width / r.width } : { x: 0, y: 40, s: 0.6 };
    stage.animate([{ transform: `translate(${f.x}px,${f.y}px) scale(${f.s})` }, { transform: 'none' }], { duration: FLY, easing: EASE });
    // the turn: it breathes in, turns over a little larger and settles
    card.animate([{ transform: 'rotateY(0) scale(1)' }, { transform: 'rotateY(0) scale(0.95)', offset: 0.16, easing: 'cubic-bezier(.45,0,.2,1)' },
      { transform: 'rotateY(180deg) scale(1.07)', offset: 0.72, easing: 'ease-out' }, { transform: 'rotateY(180deg) scale(1)' }], { duration: SPIN, delay: TURN, fill: 'both' });
    glow.animate([{ opacity: 0, transform: 'scale(0.6)' }, { opacity: 1, transform: 'scale(1)' }], { duration: 700, delay: TURN + 200, easing: 'ease-out', fill: 'both' });
    for (const [i, el] of [...wrap.querySelectorAll<HTMLElement>('.spark')].entries()) {
      const p = SPARKS[i];
      el.animate([{ opacity: 0, transform: 'translate(0,0) scale(0.2) rotate(0)' }, { opacity: 1, offset: 0.3 }, { opacity: 1, offset: 0.6 },
        { opacity: 0, transform: `translate(${p.x}px,${p.y}px) scale(${p.s}) rotate(90deg)` }], { duration: 1100 + (i % 3) * 160, delay: SHOWN - 80 + (i % 5) * 30, easing: 'cubic-bezier(.15,.7,.3,1)', fill: 'both' });
    }
    // the held breath before the turn: the seal alone moves
    wrap.querySelector('.seal')?.animate([{ transform: 'none' }, { transform: 'scale(1.12)' }, { transform: 'none' }], { duration: 300, delay: FLY, easing: 'ease-in-out' });
    for (const [i, el] of [...wrap.querySelectorAll('.up')].entries())
      el.animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }], { duration: 460, delay: SHOWN + 260 + i * 80, easing: EASE, fill: 'backwards' });
    const a = setTimeout(() => haptic.rigid(), TURN), b = setTimeout(() => { shown = true; haptic.ok(); }, SHOWN);
    return () => { clearTimeout(a); clearTimeout(b); off(); };
  });
  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: still ? 'none' : 'scale(0.96)' }], { duration: 220, easing: 'ease-in', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="scrim" bind:this={scrim} onclick={() => shown && close(overlay.id)} role="presentation"></div>
<div class="wrap" bind:this={wrap} style:--w="{W}px">
  <div class="page">
    <div class="stage" class:still bind:this={stage}>
      <span class="glow" bind:this={glow}></span><span class="shade"></span>
      {#if !still}{#each SPARKS as _, i (i)}<i class="spark"></i>{/each}{/if}
      <div class="card" bind:this={card}>
        {#if !still}<div class="face"><SantaBack w={W} /></div>{/if}
        <div class="face front">
          <Avatar person={to.person} size={Math.round(W * 0.42)} tappable={false} />
          <span class="cap t-cap">{t('santa.to')}</span>
          <b class="name">{to.person.name}</b>
        </div>
      </div>
    </div>
    <p class="wcap t-cap up">{t('santa.wishOf')}</p>
    <p class="wish t-body up">{to.wish}</p>
  </div>
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet);
    background: radial-gradient(70% 42% at 50% 40%, rgba(215, 38, 61, 0.34), transparent 72%), rgba(6, 4, 9, 0.92);
    -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); }
  :global(html.lowfx) .scrim { background: radial-gradient(70% 42% at 50% 40%, rgba(215, 38, 61, 0.3), transparent 72%), #08060B; } /* no blur there: nothing of the page shows through */
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none; display: flex; flex-direction: column; padding-bottom: var(--safe-bottom); color: #fff; text-align: center; }
  /* as the award's moment: the content scrolls in a box that ends above the home bar, a long wishlist fades out at its end */
  .page { flex: 1; min-height: 0; overflow-x: hidden; overflow-y: auto; scrollbar-width: none; pointer-events: none; display: flex; flex-direction: column; align-items: center;
    padding: calc(var(--top) + 8px) 28px 20px;
    -webkit-mask-image: linear-gradient(black calc(100% - 20px), transparent); mask-image: linear-gradient(black calc(100% - 20px), transparent); }
  .page::-webkit-scrollbar { display: none; }
  .page > :global(*) { pointer-events: auto; flex: none; }
  .page > :first-child { margin-top: auto; }
  .page > :last-child { margin-bottom: auto; }
  .stage { position: relative; width: var(--w); aspect-ratio: 3 / 4; perspective: 1100px; }
  .glow { position: absolute; inset: -42%; border-radius: 50%; background: radial-gradient(closest-side, rgba(246, 205, 120, 0.5), rgba(246, 205, 120, 0) 72%); opacity: 0; pointer-events: none; }
  /* the shadow is its own still layer: a filter on the card would flatten its two sides */
  .shade { position: absolute; inset: 10% 6% -8%; border-radius: 30%; background: rgba(0, 0, 0, 0.55); filter: blur(22px); pointer-events: none; }
  .card { position: absolute; inset: 0; transform-style: preserve-3d; }
  .face { position: absolute; inset: 0; -webkit-backface-visibility: hidden; backface-visibility: hidden; border-radius: calc(var(--w) * 0.11); }
  .front { transform: rotateY(180deg); overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: calc(var(--w) * 0.1);
    background: #FBF5EA; color: #1B1416; box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.6); }
  .front::before { content: ''; position: absolute; inset: calc(var(--w) * 0.055); border-radius: calc(var(--w) * 0.07); border: 1px solid rgba(201, 146, 54, 0.45); pointer-events: none; }
  .still .front { transform: none; }
  .still .glow { opacity: 1; }
  .cap { margin-top: calc(var(--w) * 0.075); color: #B3152C; }
  .name { max-width: 100%; margin-top: 8px; font: 800 calc(var(--w) * 0.11)/1.12 var(--font-display); letter-spacing: -0.025em; overflow-wrap: anywhere; text-wrap: balance;
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3; overflow: hidden; }
  .spark { position: absolute; left: 50%; top: 50%; width: 18px; height: 18px; margin: -9px; opacity: 0; background: #F6D58A; pointer-events: none;
    clip-path: polygon(50% 0, 60% 40%, 100% 50%, 60% 60%, 50% 100%, 40% 60%, 0 50%, 40% 40%); }
  .wcap { margin: 30px 0 8px; color: rgba(255, 255, 255, 0.55); }
  .wish { max-width: 320px; margin: 0; color: rgba(255, 255, 255, 0.92); white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
