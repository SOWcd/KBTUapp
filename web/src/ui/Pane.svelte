<script lang="ts">
  // A page pushed over another, the phone's own way (Settings' rows, owner Oct 30: "like Apple"; a sheet from below read
  // as cheap there): it slides in from the right while the page under it drifts left; "‹ Back", Telegram's Back or a
  // swipe from the left edge takes it away the same road.
  import type { Component, Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import { removeOverlay, close, hideChrome, type Overlay } from '../lib/state/ui.svelte';

  let { overlay, title, icon, back, children }: { overlay: Overlay; title: string; icon?: Component<any>; back: string; children: Snippet } = $props();
  $effect(() => { overlay.title = title; overlay.icon = icon; });

  let el: HTMLDivElement;
  let gone = false, dx = 0, x0: number | null = null;
  const EASE = 'cubic-bezier(.32,.72,0,1)';
  const ms = (n: number) => (matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : n);
  // the page under it drifts left while one is up (base.css html[data-pane]), once per pane however it leaves
  const d = document.documentElement.dataset;
  let counted = false;
  const unpane = () => { if (!counted) return; counted = false; const n = Number(d.pane || 1) - 1; if (n > 0) d.pane = String(n); else delete d.pane; };

  onMount(() => {
    const undo = hideChrome();
    d.pane = String(Number(d.pane || 0) + 1); counted = true;
    el.animate([{ transform: 'translate3d(100%,0,0)' }, { transform: 'translate3d(0,0,0)' }], { duration: ms(440), easing: EASE });
    return () => { undo(); unpane(); };
  });
  function leave() {
    if (gone) return;
    gone = true; unpane();
    const a = el.animate([{ transform: `translate3d(${dx}px,0,0)` }, { transform: 'translate3d(100%,0,0)' }], { duration: ms(320), easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });

  // a swipe from the left edge follows the finger; past a third of the width (or a flick) it goes, else it springs back
  let t0 = 0;
  function down(e: PointerEvent) { if (e.clientX < 24 && !(e.target as Element).closest('button, input, a')) { x0 = e.clientX; t0 = e.timeStamp; el.setPointerCapture(e.pointerId); } }
  function move(e: PointerEvent) { if (x0 == null) return; dx = Math.max(0, e.clientX - x0); el.style.transform = `translate3d(${dx}px,0,0)`; }
  function up(e: PointerEvent) {
    if (x0 == null) return;
    x0 = null;
    if (dx > el.clientWidth / 3 || dx / Math.max(1, e.timeStamp - t0) > 0.6) { close(overlay.id, true); return; }
    el.animate([{ transform: `translate3d(${dx}px,0,0)` }, { transform: 'translate3d(0,0,0)' }], { duration: ms(260), easing: EASE });
    el.style.transform = ''; dx = 0;
  }
</script>

<div class="pane scroll" role="region" aria-label={title} bind:this={el} onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
  <button class="back" onclick={() => close(overlay.id, true)}><ChevronLeft size={26} strokeWidth={2.2} />{back}</button>
  <h1 class="ttl">{title}</h1>
  {@render children()}
  <div class="tail"></div>
</div>

<style>
  .pane { position: fixed; inset: 0; z-index: var(--z-sheet); padding: var(--page-top) var(--gutter) 0; background: var(--bg);
    box-shadow: -18px 0 40px -16px rgba(0, 0, 0, 0.45); touch-action: pan-y; }
  .back { display: inline-flex; align-items: center; gap: 0; margin: -6px 0 0 -8px; height: 36px; padding-right: 8px;
    color: var(--accent-text); font: 500 17px/1 var(--font-text); }
  .back:active { opacity: 0.5; }
  .ttl { margin: 8px 4px 18px; font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .tail { height: calc(var(--safe-bottom) + 40px); }
</style>
