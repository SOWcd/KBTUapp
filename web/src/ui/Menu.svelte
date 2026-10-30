<script lang="ts">
  // The iOS pull-down (open it with menu() from ui/menu.ts, never directly): anchored at a row's value or a ⋯ button,
  // under it, or above it when there is no room below (a bottom row at 320 px); it grows out of the anchor. Items: a
  // check on the current choice, an icon at the end, destructive ones last in red after a line. A tap outside, Escape
  // and Telegram's Back close it (an overlay in the stack); focus goes to the current choice and back to the anchor.
  // The glass look without the tilt light (use:glass is a measured cost on a surface this short-lived).
  import { onMount, flushSync } from 'svelte';
  import Check from '@lucide/svelte/icons/check';
  import { close, removeOverlay, type Overlay } from '../lib/state/ui.svelte';
  import { haptic } from '../lib/tg';
  import type { MenuItem } from './menu';

  let { overlay, anchor, items, align }: { overlay: Overlay; anchor: Element; items: MenuItem[]; align?: 'start' | 'end' } = $props();

  const actions = $derived(items.filter((i) => !i.destructive));
  const red = $derived(items.filter((i) => i.destructive));
  const picks = $derived(items.some((i) => i.checked !== undefined)); // a column for the check, so the labels line up

  let layer: HTMLDivElement, panel: HTMLDivElement, room: HTMLElement;
  let gone = false;
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  onMount(() => {
    const L = layer.getBoundingClientRect(), a = anchor.getBoundingClientRect(), R = room.getBoundingClientRect();
    // the room it may take: under Telegram's header row, above the home indicator, and within what the keyboard leaves
    const vv = window.visualViewport;
    const top = Math.max(R.top, vv ? vv.offsetTop : -Infinity), bottom = Math.min(R.bottom, vv ? vv.offsetTop + vv.height : Infinity);
    const w = panel.offsetWidth, h = panel.offsetHeight, gap = 6, edge = 10;
    const end = align ? align === 'end' : a.left + a.width / 2 > L.left + L.width / 2;
    const x = Math.max(edge, Math.min(L.width - w - edge, (end ? a.right - w : a.left) - L.left));
    const below = bottom - a.bottom - gap - edge, above = a.top - top - gap - edge;
    const down = h <= below || below >= above;
    const fit = Math.max(88, Math.min(h, down ? below : above));
    panel.style.left = `${x}px`;
    panel.style.top = `${down ? a.bottom - L.top + gap : a.top - L.top - gap - fit}px`;
    if (fit < h) panel.style.maxHeight = `${fit}px`;
    panel.style.transformOrigin = `${Math.max(0, Math.min(w, a.left + a.width / 2 - L.left - x))}px ${down ? 0 : fit}px`;
    panel.style.visibility = '';
    if (!still()) {
      panel.animate([{ transform: 'scale(0.4)' }, { transform: 'scale(1)' }], { duration: 420, easing: 'cubic-bezier(.3, 1.3, .5, 1)' });
      panel.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160, easing: 'ease-out' });
    }
    (panel.querySelector<HTMLElement>('[aria-checked="true"]:not(:disabled)') ?? panel.querySelector<HTMLElement>('button:not(:disabled)'))?.focus({ preventScroll: true });
  });

  // back to the anchor, unless something else took the focus meanwhile (a sheet the pick opened)
  function refocus() {
    const f = document.activeElement;
    const to = anchor.closest<HTMLElement>('button, a, [tabindex]'); // a row's value span: its row
    if ((!f || f === document.body || layer.contains(f)) && to?.isConnected) to.focus({ preventScroll: true });
  }
  function leave() {
    if (gone) return;
    gone = true;
    const done = () => { refocus(); removeOverlay(overlay.id); };
    if (still()) return done();
    panel.animate([{ opacity: 1, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(0.92)' }], { duration: 150, easing: 'ease-in', fill: 'forwards' }).onfinish = done;
  }
  $effect(() => { if (overlay.closing) leave(); });

  function pick(it: MenuItem) {
    if (it.disabled || gone) return;
    haptic.select();
    if (it.instant) { gone = true; refocus(); removeOverlay(overlay.id); flushSync(); }
    else close(overlay.id, false);
    it.onselect();
  }

  function key(e: KeyboardEvent) {
    const all = [...panel.querySelectorAll<HTMLElement>('button:not(:disabled)')];
    const i = all.indexOf(document.activeElement as HTMLElement);
    const go = (j: number) => { e.preventDefault(); all[(j + all.length) % all.length]?.focus(); };
    if (e.key === 'ArrowDown') go(i + 1);
    else if (e.key === 'ArrowUp') go(i - 1);
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(all.length - 1);
    else if (e.key === 'Tab') { e.preventDefault(); close(overlay.id, true); }
  }
</script>

<div class="layer" bind:this={layer}>
  <div class="catch" onclick={() => close(overlay.id, true)} role="presentation"></div><!-- the outside tap stops here: it never reaches what's under -->
  <i class="room" bind:this={room}></i>
  <div class="menu glass glass-sheet" role="menu" tabindex="-1" bind:this={panel} style="visibility:hidden" onkeydown={key}>
    {#each [actions, red] as group, g (g)}
      {#if g && group.length && actions.length}<div class="sep" role="separator"></div>{/if}
      {#each group as it (it.label)}
        <button class="it" class:red={it.destructive} class:picks role={it.checked === undefined ? 'menuitem' : 'menuitemradio'} aria-checked={it.checked}
          disabled={it.disabled} onclick={() => pick(it)}>
          {#if picks}<span class="ck">{#if it.checked}<Check size={18} strokeWidth={2.4} />{/if}</span>{/if}
          <span class="lb">{it.label}</span>
          {#if it.icon}{@const Icon = it.icon}<span class="ic"><Icon size={20} strokeWidth={2} /></span>{/if}
        </button>
      {/each}
    {/each}
  </div>
</div>

<style>
  .layer { position: absolute; inset: 0; z-index: calc(var(--z-sheet) + 6); } /* over a sheet and the capsule above it */
  .catch { position: absolute; inset: 0; }
  .room { position: absolute; top: max(var(--top), var(--head-bottom)); bottom: var(--safe-bottom); left: 0; width: 0; visibility: hidden; pointer-events: none; }
  .menu { position: absolute; background-color: var(--menu-bg); min-width: 220px; max-width: min(290px, calc(100% - 20px)); padding: 6px; border-radius: var(--r-l);
    overflow-y: auto; overscroll-behavior: contain; scrollbar-width: none; }
  .menu:focus { outline: none; }
  .it { position: relative; display: flex; align-items: center; gap: 10px; width: 100%; min-height: var(--ctl-m); padding: 10px 12px; border-radius: var(--r-m);
    font: 450 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.012em; color: var(--text); text-align: left; transition: background-color var(--t-fast); }
  .it.picks { padding-left: 8px; }
  .it:active:not(:disabled), .it:focus-visible { background: var(--fill); outline: none; transform: none; opacity: 1; }
  @media (hover: hover) { .it:hover:not(:disabled) { background: var(--fill); } }
  .it:disabled { color: var(--text-3); cursor: default; }
  .red { color: var(--danger-text); }
  .ck { flex: none; display: inline-flex; width: 20px; }
  .lb { flex: 1; min-width: 0; overflow-wrap: break-word; hyphens: auto; }
  .ic { flex: none; display: inline-flex; }
  .sep { height: 0.5px; margin: 6px 12px; background: var(--separator); }
</style>
