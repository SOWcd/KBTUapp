<script lang="ts">
  // Bottom sheet (liquid glass without the light spot, floats above everything). Closes by Telegram's Back button, a tap on the
  // scrim, or a pull down — from the grip, or from the content when it is scrolled to the top.
  // The drag writes transform directly (no reactive state per frame); exit runs, then the overlay
  // is removed from the stack.
  import type { Component, Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import { removeOverlay, close, hideChrome, type Overlay } from '../lib/state/ui.svelte';
  import X from '@lucide/svelte/icons/x';
  import { haptic, inTelegram } from '../lib/tg';
  import { sheets } from '../lib/state/sheets';
  import { t } from '../lib/i18n/index.svelte';
  import { glass } from './glass';

  // title: what the capsule says while this sheet is on top (SPEC §8.2); icon: a small mark before it (settings)
  // hold: while it says true, a close (Back, scrim, pull) is turned back — the sheet springs home and onhold runs (ask first).
  // Without one, text typed here and not sent asks before a hand closes it (a pull lost a club's application).
  // see: the page stays bright above it and the sheet takes at most the lower part, so what it changes shows live above
  // (my lanyard while I dress it)
  // Sizes by one rule: WORK (many steps, minutes: admin, registry, event management, forms) is `full`,
  // the whole screen under the capsule, closed by Back only (a pull must not drop work); LOOKING at one thing is `tall`,
  // up to the capsule; ONE DECISION is neither: as tall as its content.
  type Props = { overlay: Overlay; title?: string; icon?: Component<any>; tint?: string | null; tall?: boolean; full?: boolean; see?: boolean; children: Snippet; footer?: Snippet; hold?: () => boolean; onhold?: () => void };
  let { overlay, title = '', icon, tint = null, tall = false, full = false, see = false, children, footer, hold, onhold }: Props = $props();
  $effect(() => { overlay.title = title; overlay.icon = icon; });

  let panel: HTMLDivElement;
  let scrim: HTMLDivElement;
  let body: HTMLDivElement;
  let gone = false;

  // the rise, and any height change after it, on one spring. The panel sits on the bottom edge, so a taller one would
  // put its top edge higher in one frame (details arriving after it opened: a person's card, a club); instead an added
  // offset holds the top edge where it was and lets it glide to its new place (FLIP), mid-rise or after. Its own
  // property (translate, added on), so the rise runs on untouched; the rise in pixels: a percentage of the height
  // would jump with it.
  let lift: Animation | null = null, height = 0;
  const root = getComputedStyle(document.documentElement), slow = root.getPropertyValue('--t-slow').trim();
  const RISE = (parseFloat(slow) || 0.38) * (slow.endsWith('ms') ? 1 : 1000), SPRING = root.getPropertyValue('--ease-spring').trim() || 'ease-out';
  const motion = () => ({ duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : RISE, easing: SPRING });
  // the first call comes after the browser's own layout and before the first paint: the rise starts there, with the
  // height already known (reading it at mount forced a layout of the whole sheet a step early)
  function resized() {
    const h = panel.getBoundingClientRect().height, dh = h - height;
    if (!lift) { height = h; lift = panel.animate([{ transform: `translate3d(0,${h}px,0)` }, { transform: 'translate3d(0,0,0)' }], motion()); return; }
    height = h;
    if (Math.abs(dh) < 2 || gone || dragging || currentY) return;
    panel.animate([{ translate: `0 ${dh}px` }, { translate: '0 0' }], { ...motion(), composite: 'add' });
  }

  function leave(fromY = 0) {
    if (gone) return;
    gone = true;
    lift?.cancel();
    const h = panel.getBoundingClientRect().height;
    const a = panel.animate([{ transform: `translate3d(0,${fromY}px,0)` }, { transform: `translate3d(0,${h + 40}px,0)` }],
      { duration: 260, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }

  // each text field's value when first focused: a changed one is unsent text (a sent draft is cleared, so it doesn't ask);
  // a search field never counts
  const was = new Map<HTMLInputElement | HTMLTextAreaElement, string>();
  function focusin(e: FocusEvent) {
    const el = e.target;
    const text = el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && /^(text|url|email|tel|number|)$/.test(el.getAttribute('type') ?? '') && el.enterKeyHint !== 'search');
    if (text && !was.has(el)) was.set(el, el.value);
  }
  const typed = () => !!overlay.byUser && [...was].some(([el, v]) => el.isConnected && el.value.trim() !== v.trim());
  async function askLeave() {
    if (await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('common.cancel'), danger: true })) close(overlay.id);
  }

  $effect(() => {
    if (!overlay.closing) return;
    if (hold ? hold() : typed()) {
      overlay.closing = false;
      panel.style.transition = 'transform 320ms cubic-bezier(.32,.72,0,1)';
      panel.style.transform = 'translate3d(0,0,0)';
      currentY = 0;
      (hold ? onhold : askLeave)?.();
      return;
    }
    leave(currentY);
  });

  // ---- pull to close ----
  let startX = 0, startY = 0, currentY = 0, dragging = false, decided = false, lastY = 0, lastT = 0, v = 0;
  function onStart(e: TouchEvent) {
    if (full || e.touches.length !== 1) return;
    const inBody = body.contains(e.target as Node);
    if (inBody && body.scrollTop > 0) return; // the list scrolls first
    if ((e.target as Element).closest?.('textarea, [role=slider]')) return; // a long text scrolls itself (dragging it closed the memo); a slider drags its own way
    startX = e.touches[0].clientX; startY = lastY = e.touches[0].clientY; lastT = performance.now(); v = 0;
    dragging = true; decided = false; currentY = 0;
  }
  function onMove(e: TouchEvent) {
    if (!dragging) return;
    const y = e.touches[0].clientY, dy = y - startY;
    if (!decided) {
      const dx = e.touches[0].clientX - startX;
      if (Math.abs(dy) < 6 && Math.abs(dx) < 6) return;
      decided = true;
      if (dy < 0 || Math.abs(dx) > Math.abs(dy)) { dragging = false; return; } // upward: let the content scroll; sideways: a swipe of its own (a comment's reply)
    }
    if (e.cancelable) e.preventDefault();
    const now = performance.now();
    v = (y - lastY) / Math.max(1, now - lastT); lastY = y; lastT = now;
    currentY = Math.max(0, dy);
    panel.style.transition = 'none';
    panel.style.transform = `translate3d(0,${currentY}px,0)`;
  }
  function onEnd() {
    if (!dragging) return;
    dragging = false;
    if (!decided) return;
    if (currentY > 120 || v > 0.6) { haptic.soft(); close(overlay.id, true); return; }
    panel.style.transition = 'transform 320ms cubic-bezier(.32,.72,0,1)';
    panel.style.transform = 'translate3d(0,0,0)';
    currentY = 0;
  }

  // keyboard and screen readers: focus goes into the sheet as it opens (unless a field in it took it) and back to what
  // opened it when it goes (never to a text field: that would bring the keyboard up)
  onMount(() => {
    const opener = document.activeElement as HTMLElement | null;
    if (!panel.contains(document.activeElement)) panel.focus({ preventScroll: true });
    const back = () => { if (opener?.isConnected && !opener.matches('input, textarea, [contenteditable]')) opener.focus({ preventScroll: true }); };
    const ro = new ResizeObserver(resized);
    ro.observe(panel);
    panel.addEventListener('touchstart', onStart, { passive: true });
    panel.addEventListener('touchmove', onMove, { passive: false });
    panel.addEventListener('touchend', onEnd);
    panel.addEventListener('touchcancel', onEnd);
    panel.addEventListener('focusin', focusin);
    const chrome = hideChrome();
    return () => { ro.disconnect(); chrome(); back(); };
  });
</script>

<div class="scrim" class:clear={see} bind:this={scrim} onclick={() => close(overlay.id, true)} role="presentation"></div>
<div class="sheet glass glass-sheet" use:glass class:tall class:full class:see class:hasfoot={!!footer} bind:this={panel} role="dialog" aria-modal="true" aria-label={title || undefined} tabindex="-1" style={tint ? `--tint:${tint}` : ''}>
  {#if tint}<div class="tint" aria-hidden="true"></div>{/if}
  {#if !full}<div class="grip" aria-hidden="true"></div>
  {:else if !inTelegram}<button class="x" onclick={() => close(overlay.id, true)} aria-label={t('common.close')}><X size={22} /></button>{/if}<!-- no Back button in a browser: the only way out -->
  <div class="body scroll" bind:this={body}>{@render children()}</div>
  {#if footer}<div class="foot">{@render footer()}</div>{/if}
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--scrim); animation: fade var(--t-base) ease-out both; }
  /* never above the capsule: outside Telegram (a browser) the top band is 0, the capsule still takes 46 px */
  .sheet {
    position: absolute; left: 0; right: 0; bottom: 0; z-index: var(--z-sheet);
    max-width: 560px; margin: 0 auto; max-height: calc(100% - max(var(--top), 48px) - 10px);
    display: flex; flex-direction: column; overflow: hidden;
    border-radius: var(--r-xl) var(--r-xl) 0 0;
    will-change: transform;
  }
  .tall { height: calc(100% - max(var(--top), 48px) - 10px); }
  .sheet:focus { outline: none; }
  .full { top: 0; max-height: none; max-width: none; border-radius: 0; background: var(--glow), var(--bg); -webkit-backdrop-filter: none; backdrop-filter: none; }
  .full::before, .full::after { display: none; }
  .full .body { padding-top: var(--page-top); }
  .x { position: absolute; top: calc(var(--safe-top) + 4px); left: 12px; z-index: 1; width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--surface); color: var(--text); }
  .scrim.clear { background: transparent; }
  .see { max-height: 56%; }
  .tint {
    position: absolute; inset: 0 0 auto; height: 320px; pointer-events: none;
    background: linear-gradient(180deg, var(--tint), transparent);
    opacity: 0.5;
  }
  .grip { position: relative; flex: none; width: 38px; height: 5px; border-radius: 3px; background: var(--line-2); margin: 8px auto 4px; }
  .body { position: relative; flex: 1; padding: 6px var(--gutter) calc(var(--s-6) + var(--safe-bottom)); }
  .foot {
    position: relative; flex: none; padding: var(--s-3) var(--gutter) calc(var(--s-3) + var(--safe-bottom));
    border-top: 1px solid var(--line);
  }
  .hasfoot .body { padding-bottom: var(--s-4); }
  @keyframes fade { from { opacity: 0; } }
</style>
