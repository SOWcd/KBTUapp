<script lang="ts">
  // A page pushed over another, the phone's own way (Settings' rows, owner Oct 30: "like Apple"; a sheet from below read
  // as cheap there): it slides in from the right while the page under it (a tab, a sheet, another pane) drifts left;
  // "‹ Back", Telegram's Back or a swipe from the left edge takes it away the same road. Its large title fits its line
  // (34 down to 24); the capsule shows the live status or nothing until that title scrolls away, then the title.
  // Text typed and not sent asks before a hand closes it, as in a Sheet.
  import type { Component, Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import { removeOverlay, close, hideChrome, type Overlay } from '../lib/state/ui.svelte';
  import { fitTitle, largeTitle } from './title';
  import { unsent } from './guard';

  let { overlay, title, icon, back, children }: { overlay: Overlay; title: string; icon?: Component<any>; back: string; children: Snippet } = $props();
  $effect(() => { overlay.title = title; overlay.icon = icon; });

  let el: HTMLDivElement;
  let gone = false, dx = 0, x0: number | null = null;
  let scrolled = $state(false);
  const EASE = 'cubic-bezier(.32,.72,0,1)';
  const ms = (n: number) => (matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : n);
  const guard = unsent(() => overlay);

  // the page under it drifts left and dims (base.css .pane-under), whatever it is; back in place however this one leaves
  let under: Element | null = null;
  function drift() {
    for (let n = el.previousElementSibling; n; n = n.previousElementSibling) {
      if (n.matches('.sheet, .pane, section.tab.on, [data-page]')) { under = n; break; }
    }
    under?.classList.add('pane-host', 'pane-under');
  }
  function undrift() {
    const u = under;
    under = null;
    if (!u) return;
    u.classList.remove('pane-under');
    setTimeout(() => { if (!u.classList.contains('pane-under')) u.classList.remove('pane-host'); }, 460);
  }

  onMount(() => {
    overlay.quiet = true; // its own title is in view at first
    const undo = hideChrome();
    drift();
    el.animate([{ transform: 'translate3d(100%,0,0)' }, { transform: 'translate3d(0,0,0)' }], { duration: ms(440), easing: EASE });
    el.addEventListener('focusin', guard.focusin);
    return () => { undo(); undrift(); };
  });
  function leave() {
    if (gone) return;
    gone = true; undrift();
    const a = el.animate([{ transform: `translate3d(${dx}px,0,0)` }, { transform: 'translate3d(100%,0,0)' }], { duration: ms(320), easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => {
    if (!overlay.closing) return;
    if (guard.typed()) { overlay.closing = false; el.style.transform = ''; dx = 0; guard.ask(); return; }
    leave();
  });

  // a swipe from the left edge follows the finger; past a third of the width (or a flick) it goes, else it springs back
  let t0 = 0;
  function down(e: PointerEvent) { if (e.clientX < 24 && !(e.target as Element).closest('button, input, a')) { x0 = e.clientX; t0 = e.timeStamp; el.setPointerCapture(e.pointerId); } }
  function move(e: PointerEvent) { if (x0 == null) return; dx = Math.max(0, e.clientX - x0); el.style.transform = `translate3d(${dx}px,0,0)`; }
  function up(e: PointerEvent) {
    if (x0 == null) return;
    x0 = null;
    if (dx > el.clientWidth / 3 || dx / Math.max(1, e.timeStamp - t0) > 0.6) { close(overlay.id, true); if (overlay.closing) return; }
    el.animate([{ transform: `translate3d(${dx}px,0,0)` }, { transform: 'translate3d(0,0,0)' }], { duration: ms(260), easing: EASE });
    el.style.transform = ''; dx = 0;
  }
</script>

<div class="pane scroll" class:scrolled role="region" aria-label={title} bind:this={el} onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}
  onscroll={() => { if (scrolled !== el.scrollTop > 2) scrolled = !scrolled; }}>
  <button class="back" onclick={() => close(overlay.id, true)}><ChevronLeft size={26} strokeWidth={2.2} />{back}</button>
  <h1 class="ttl" use:fitTitle use:largeTitle={(g) => (overlay.quiet = !g)}>{title}</h1>
  {@render children()}
  <div class="tail"></div>
</div>

<style>
  .pane { position: fixed; inset: 0; z-index: var(--z-sheet); padding: var(--page-top) var(--gutter) 0; background: var(--bg);
    box-shadow: -18px 0 40px -16px rgba(0, 0, 0, 0.45); touch-action: pan-y; }
  /* the scroll edge: content fades out under the capsule instead of running into it */
  .scrolled { -webkit-mask-image: linear-gradient(transparent calc(var(--head-bottom) - 4px), black var(--page-top));
    mask-image: linear-gradient(transparent calc(var(--head-bottom) - 4px), black var(--page-top)); }
  .back { position: relative; display: inline-flex; align-items: center; gap: 0; margin: -6px 0 0 -8px; height: 36px; padding-right: 8px;
    color: var(--accent-text); font: 500 var(--fs-row)/1 var(--font-text); }
  .back::after { content: ''; position: absolute; inset: -4px 0; } /* 36 seen, 44 to the finger */
  .back:active { opacity: 0.5; }
  .ttl { margin: 8px 4px 18px; font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; overflow-wrap: break-word; }
  .tail { height: calc(var(--safe-bottom) + 40px); }
</style>
