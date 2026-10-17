<script lang="ts">
  // Bottom nav (liquid glass, floats). Three equal tabs that stay put (the owner's pick of four layouts,
  // Oct 4: a widening active tab made the others jump on every switch); the active one shows its label
  // inside one pill that slides under it with a jelly squash. Press and drag along the bar previews tabs;
  // the tab switches on release. Shrinks to icons while scrolling down; hides under a sheet. Over the
  // Feed it turns into dark glass tinted by the slide, in step with the finger (chrome.ts).
  import Ticket from '@lucide/svelte/icons/ticket';
  import Landmark from '@lucide/svelte/icons/landmark';
  import UserRound from '@lucide/svelte/icons/circle-user-round';
  import { ui, TABS, goTab } from '../lib/state/ui.svelte';
  import { haptic } from '../lib/tg';
  import { t } from '../lib/i18n/index.svelte';
  import { glass, refract, jelly } from './glass';
  import { chrome } from './chrome';

  let { labels, dot = [false, false, false] }: { labels: [string, string, string]; dot?: boolean[] } = $props();

  let preview = $state<number | null>(null);
  const shown = $derived(preview ?? TABS.indexOf(ui.tab));

  let bar: HTMLElement;
  let pill: HTMLSpanElement;
  $effect(() => { void shown; jelly(pill); });
  let drag: null | { x: number; on: boolean; id: number } = null;
  const idxAt = (x: number) => { const r = bar.getBoundingClientRect(); return Math.max(0, Math.min(2, Math.floor(((x - r.left) / r.width) * 3))); };
  function down(e: PointerEvent) { drag = { x: e.clientX, on: false, id: e.pointerId }; }
  function moveP(e: PointerEvent) {
    if (!drag) return;
    if (!drag.on) { if (Math.abs(e.clientX - drag.x) < 8) return; drag.on = true; bar.setPointerCapture(drag.id); }
    const i = idxAt(e.clientX);
    if (i !== preview) { preview = i; haptic.select(); }
  }
  function up() {
    const d = drag; drag = null;
    if (d?.on && preview != null) { const i = preview; preview = null; goTab(TABS[i]); }
    else preview = null;
  }
  function pick(i: number) { if (drag?.on) return; goTab(TABS[i]); ui.awake++; }
</script>

<nav class="nav glass glass-pill" class:mini={ui.navMini} bind:this={bar} aria-label={t('nav.label')} use:glass={{ bloom: true }} use:refract use:chrome
     onpointerdown={down} onpointermove={moveP} onpointerup={up} onpointercancel={up}>
  <span class="tone-base" aria-hidden="true"></span><span class="tone-feed" aria-hidden="true"></span>
  <span class="pill" bind:this={pill} style="left:calc(4px + (100% - 8px) * {shown} / 3)" aria-hidden="true"></span>
  {#each TABS as tab, i (tab)}
    <button class="tab" class:on={shown === i} aria-current={ui.tab === tab ? 'page' : undefined} onclick={() => pick(i)}>
      <span class="ic">
        {#if i === 0}<Ticket size={22} strokeWidth={1.9} />{:else if i === 1}<Landmark size={22} strokeWidth={1.9} />{:else}<UserRound size={22} strokeWidth={1.9} />{/if}
        {#if dot[i]}<i class="dot"></i>{/if}
      </span>
      <span class="lbl">{labels[i]}</span>
    </button>
  {/each}
</nav>

<style>
  .nav {
    position: absolute; left: 50%; bottom: calc(var(--safe-bottom) + 10px); z-index: var(--z-nav);
    width: min(360px, calc(100% - 32px)); height: 60px; padding: 4px; border-radius: var(--r-full);
    display: flex; transform: translateX(-50%); touch-action: none; overflow: hidden;
    /* the capsule's clear glass (owner, Oct 4: on the big bar the dark frosted body read as plastic) */
    /* calmer than it was (owner, Oct 13: what scrolled under it smeared through "crookedly"): a stronger blur, less
       saturation; still the one backdrop filter, the rim and glow below are plain paint */
    -webkit-backdrop-filter: blur(20px) saturate(160%) brightness(1.04);
    backdrop-filter: var(--refract, blur(20px) saturate(160%) brightness(1.04));
    background: none;
    box-shadow: 0 12px 32px -10px rgba(0, 0, 0, 0.55), 0 0 24px -6px var(--nav-glow, rgba(120, 150, 255, 0.4));
    transition: transform var(--t-slow) var(--ease-spring), height var(--t-base) var(--ease), width var(--t-base) var(--ease);
  }
  /* an edge all the way round (owner, Oct 13: "the bar has no edges"; the shared rim lit only the top-left corner),
     brightest on top, the colour fringes at the sides */
  .nav::after {
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.8), rgba(255, 255, 255, 0.2) 45%, rgba(255, 255, 255, 0.34)),
      linear-gradient(90deg, rgba(255, 120, 200, 0.5), transparent 20%, transparent 80%, rgba(90, 190, 255, 0.55));
  }
  .nav > .tone-base { background: var(--glass-clear); }
  .nav > .tone-feed { background-color: rgb(var(--feed-rgb, 24 28 44) / 0.55); background-image: linear-gradient(120deg, transparent, rgba(12, 14, 24, 0.6)); }
  /* past the halfway point to the Feed: the dark palette (chrome.ts sets data-feed) */
  .nav:global([data-feed]) { --text: #FFFFFF; --text-2: rgba(255, 255, 255, 0.72); --bg: #0A0F24; --chrome-ink: rgba(255, 255, 255, 0.85); }
  .nav.mini { height: 50px; width: min(250px, calc(100% - 64px)); }
  :global(html[data-sheet]) .nav { transform: translate(-50%, calc(100% + 40px)); }
  .pill {
    position: absolute; top: 4px; bottom: 4px; width: calc((100% - 8px) / 3); border-radius: var(--r-full); background: var(--text);
    transition: left 380ms var(--ease-spring), background-color 200ms ease;
  }
  .tab {
    position: relative; flex: 1 1 0; min-width: 0; padding: 0 6px; display: flex; align-items: center; justify-content: center; gap: 0;
    color: var(--chrome-ink); border-radius: var(--r-full);
    transition: color var(--t-base) var(--ease), gap 380ms var(--ease-spring), transform 350ms cubic-bezier(.3, 1.6, .5, 1);
  }
  .tab:active { transform: scale(0.94); transition-duration: var(--t-base), 380ms, 80ms; }
  .tab.on { color: var(--bg); gap: 7px; }
  .ic { position: relative; display: inline-flex; flex: none; }
  .dot { position: absolute; top: -1px; right: -2px; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); box-shadow: 0 0 0 2px var(--glass-bg); }
  .lbl {
    max-width: 0; opacity: 0; overflow: hidden; white-space: nowrap;
    font: 650 14px/1 var(--font-text); letter-spacing: -0.01em;
    transition: max-width 380ms var(--ease-spring), opacity var(--t-base) var(--ease);
  }
  .tab.on .lbl { max-width: 120px; opacity: 1; }
  .mini .tab.on .lbl { max-width: 0; opacity: 0; }
  .mini .tab.on { gap: 0; }
  /* a 320-px phone: a third of the bar is ~93 px, so the longest label (Russian "Join") gets a size smaller */
  @media (max-width: 359px) { .tab { padding: 0 2px; } .tab.on { gap: 5px; } .lbl { font-size: 13px; letter-spacing: -0.02em; } }
</style>
