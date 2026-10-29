<script lang="ts">
  // Bottom nav (liquid glass, floats). Equal tabs that stay put (four since the forum, Oct 30) (the owner's pick of four layouts,
  // Oct 4: a widening active tab made the others jump on every switch); the active one shows its label
  // inside one pill that slides under it with a jelly squash. Press and drag along the bar previews tabs;
  // the tab switches on release. Shrinks to icons while scrolling down; hides under a sheet. Over the
  // Feed it turns into dark glass tinted by the slide, in step with the finger (chrome.ts).
  import Ticket from '@lucide/svelte/icons/ticket';
  import Landmark from '@lucide/svelte/icons/landmark';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import UserRound from '@lucide/svelte/icons/circle-user-round';
  import MapIcon from '@lucide/svelte/icons/map';
  import { sheets, mapFrom, copyCap } from '../lib/state/sheets';
  import { ui, goTab, type Tab } from '../lib/state/ui.svelte';
  import { haptic } from '../lib/tg';
  import { t } from '../lib/i18n/index.svelte';
  import { glass, refract, jelly } from './glass';
  import { chrome } from './chrome';

  // the tabs shown (the forum only where the server opened it), each with its label and dot
  let { tabs, labels, dot = [] }: { tabs: Tab[]; labels: string[]; dot?: boolean[] } = $props();
  const N = $derived(tabs.length);
  const ICON = { afisha: Ticket, forum: MessagesSquare, club: Landmark, profile: UserRound };

  let preview = $state<number | null>(null);
  const shown = $derived(preview ?? tabs.indexOf(ui.tab));

  let bar: HTMLElement;
  let pill: HTMLSpanElement;
  $effect(() => { void shown; jelly(pill); });
  let drag: null | { x: number; on: boolean; id: number } = null;
  const idxAt = (x: number) => { const r = bar.getBoundingClientRect(); return Math.max(0, Math.min(N - 1, Math.floor(((x - r.left) / r.width) * N))); };
  function down(e: PointerEvent) { drag = { x: e.clientX, on: false, id: e.pointerId }; }
  function moveP(e: PointerEvent) {
    if (!drag) return;
    if (!drag.on) { if (Math.abs(e.clientX - drag.x) < 8) return; drag.on = true; bar.setPointerCapture(drag.id); }
    const i = idxAt(e.clientX);
    if (i !== preview) { preview = i; haptic.select(); }
  }
  function up() {
    const d = drag; drag = null;
    if (d?.on && preview != null) { const i = preview; preview = null; goTab(tabs[i]); }
    else preview = null;
  }
  // the button gives under the finger and springs back as the map grows out of it (CampusMap's iris)
  function openMap(e: MouseEvent) {
    const b = e.currentTarget as HTMLElement, r = b.getBoundingClientRect();
    mapFrom.at = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    mapFrom.cap = copyCap();
    b.animate([{ transform: 'scale(1)' }, { transform: 'scale(0.84)', offset: 0.35 }, { transform: 'scale(1.06)', offset: 0.75 }, { transform: 'scale(1)' }], { duration: 320, easing: 'ease-out' });
    sheets.map();
  }
  // the map's chunk on the press, not the click: by the release it has been loading for the whole press
  const warm = () => { void import('../screens/map/CampusMap.svelte').catch(() => {}); };
  function pick(i: number) { if (drag?.on) return; goTab(tabs[i]); ui.awake++; }
</script>

<div class="dock">
<nav class="nav glass glass-pill" class:mini={ui.navMini} bind:this={bar} aria-label={t('nav.label')} use:glass={{ bloom: true }} use:refract use:chrome
     onpointerdown={down} onpointermove={moveP} onpointerup={up} onpointercancel={up}>
  <span class="tone-base" aria-hidden="true"></span><span class="tone-feed" aria-hidden="true"></span>
  <span class="pill" bind:this={pill} style="left:calc(4px + (100% - 8px) * {shown} / {N}); width:calc((100% - 8px) / {N})" aria-hidden="true"></span>
  {#each tabs as tab, i (tab)}
    {@const Icon = ICON[tab]}
    <button class="tab" class:on={shown === i} aria-current={ui.tab === tab ? 'page' : undefined} onclick={() => pick(i)}>
      <span class="ic">
        <Icon size={22} strokeWidth={1.9} />
        {#if dot[i]}<i class="dot"></i>{/if}
      </span>
      <span class="lbl">{labels[i]}</span>
    </button>
  {/each}
</nav>
<!-- the map beside the tabs, under the thumb on every screen (the button at the top of Today was hard
     to find); a round glass button of its own, like iOS 26's search, so the three tabs keep their width -->
<button class="mapb glass glass-pill" class:mini={ui.navMini} aria-label={t('map.open')} use:glass={{ bloom: true }} use:chrome
        onpointerdown={warm} onclick={openMap}>
  <span class="tone-base" aria-hidden="true"></span><span class="tone-feed" aria-hidden="true"></span>
  <MapIcon size={22} strokeWidth={1.9} />
</button>
</div>

<style>
  .dock {
    position: absolute; left: 16px; right: 16px; bottom: calc(var(--safe-bottom) + 10px); z-index: var(--z-nav);
    display: flex; justify-content: center; align-items: center; gap: 8px; pointer-events: none;
    transition: transform var(--t-slow) var(--ease-spring);
  }
  .dock > * { pointer-events: auto; }
  :global(html[data-sheet]) .dock { transform: translateY(calc(100% + 40px)); }
  .nav, .mapb {
    position: relative; flex: none; height: 60px; border-radius: var(--r-full); touch-action: none; overflow: hidden;
    /* the capsule's clear glass (on the big bar the dark frosted body read as plastic) */
    /* calmer than it was (what scrolled under it smeared through "crookedly"): a stronger blur, less
       saturation; still the one backdrop filter, the rim and glow below are plain paint */
    -webkit-backdrop-filter: blur(20px) saturate(160%) brightness(1.04);
    backdrop-filter: var(--refract, blur(20px) saturate(160%) brightness(1.04));
    background: none;
    box-shadow: 0 12px 32px -10px rgba(0, 0, 0, 0.55), 0 0 24px -6px var(--nav-glow, rgba(120, 150, 255, 0.4));
    transition: height var(--t-base) var(--ease), width var(--t-base) var(--ease);
  }
  .nav { width: min(360px, calc(100% - 68px)); padding: 4px; display: flex; container-type: inline-size; }
  .mapb { width: 60px; display: grid; place-items: center; color: var(--chrome-ink); }
  .mapb > :global(svg) { position: relative; }
  .mapb:active { transform: scale(0.94); }
  .mapb.mini { width: 50px; height: 50px; }
  /* an edge all the way round, but lit like glass, not drawn (the even
     bright outline looked fake): the shared rim's bright arc and its reflection over a faint edge, the colour fringes */
  .nav::after, .mapb::after {
    background:
      radial-gradient(ellipse 46% 140% at var(--hx) 0%, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.35) 40%, transparent 72%),
      radial-gradient(ellipse 36% 120% at var(--ox) 100%, rgba(255, 255, 255, 0.45), transparent 70%),
      linear-gradient(90deg, rgba(255, 120, 200, 0.4), transparent 18%, transparent 82%, rgba(90, 190, 255, 0.45)),
      rgba(255, 255, 255, 0.16);
  }
  .nav > .tone-base, .mapb > .tone-base { background: var(--glass-clear); }
  .nav > .tone-feed, .mapb > .tone-feed { background-color: rgb(var(--feed-rgb, 24 28 44) / 0.55); background-image: linear-gradient(120deg, transparent, rgba(12, 14, 24, 0.6)); }
  /* past the halfway point to the Feed: the dark palette (chrome.ts sets data-feed) */
  .nav:global([data-feed]), .mapb:global([data-feed]) { --text: #FFFFFF; --text-2: rgba(255, 255, 255, 0.72); --bg: #0A0F24; --chrome-ink: rgba(255, 255, 255, 0.85); }
  .nav.mini { height: 50px; width: min(250px, calc(100% - 100px)); }
  .pill {
    position: absolute; top: 4px; bottom: 4px; border-radius: var(--r-full); background: var(--text);
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
    max-width: 0; opacity: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
    font: 650 14px/1 var(--font-text); letter-spacing: -0.01em;
    transition: max-width 380ms var(--ease-spring), opacity var(--t-base) var(--ease);
  }
  .tab.on .lbl { max-width: 120px; opacity: 1; }
  .mini .tab.on .lbl { max-width: 0; opacity: 0; }
  .mini .tab.on { gap: 0; }
  /* a narrow bar (the map button beside it takes 68 px): a third of ~95 px, the longest label gets a size smaller */
  /* four tabs: a quarter of ~90 px; the longest label (Profile) gets a size smaller; a 320 px phone's bar shows the icons alone */
  @container (max-width: 380px) { .tab { padding: 0 2px; } .tab.on { gap: 5px; } .lbl { font-size: 13px; letter-spacing: -0.02em; } }
  @container (max-width: 280px) { .tab.on .lbl { max-width: 0; opacity: 0; } .tab.on { gap: 0; } }
</style>
