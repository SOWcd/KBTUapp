<script lang="ts">
  // Bottom nav (liquid glass, floats): icons only, the capsule above says the tab's name (owner, Oct 31: a label under
  // each icon only repeated it); the active one in full ink on a darker pill that slides to it with a jelly squash. Equal tabs
  // that stay put, so nothing jumps while a drag previews them. Press and drag along the bar previews tabs; the tab
  // switches on release. Shrinks while scrolling down; hides under a sheet (and the Feed). The map: its own round glass
  // button beside it.
  import MapIcon from '@lucide/svelte/icons/map';
  import { sheets, mapFrom, copyCap } from '../lib/state/sheets';
  import { ui, goTab, type Tab } from '../lib/state/ui.svelte';
  import { haptic } from '../lib/tg';
  import { t } from '../lib/i18n/index.svelte';
  import { glass, refract, jelly } from './glass';
  import { TAB_ICON } from './icons';

  // the tabs shown (the forum only where the server opened it), each with its label and dot
  let { tabs, labels, dot = [] }: { tabs: Tab[]; labels: string[]; dot?: boolean[] } = $props();
  const N = $derived(tabs.length);

  let preview = $state<number | null>(null);
  const shown = $derived(preview ?? tabs.indexOf(ui.tab));

  let bar: HTMLElement;
  let lens: HTMLSpanElement;
  $effect(() => { void shown; jelly(lens); });
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
    mapFrom.at = { x: r.left + r.width / 2, y: r.top + r.height / 2, r: r.width / 2 };
    mapFrom.cap = copyCap();
    // the bar comes back to full size under the map, so the map closes into the full button, where its own one sits
    ui.navMini = false;
    b.animate([{ transform: 'scale(1)' }, { transform: 'scale(0.84)', offset: 0.35 }, { transform: 'scale(1.06)', offset: 0.75 }, { transform: 'scale(1)' }], { duration: 320, easing: 'ease-out' });
    sheets.map();
  }
  // the map's chunk on the press, not the click: by the release it has been loading for the whole press
  const warm = () => { void import('../screens/map/CampusMap.svelte').catch(() => {}); };
  function pick(i: number) { if (drag?.on) return; goTab(tabs[i]); }
</script>

<div class="dock">
<nav class="nav glass glass-pill" class:mini={ui.navMini} bind:this={bar} aria-label={t('nav.label')} use:glass={{ bloom: true }} use:refract
     onpointerdown={down} onpointermove={moveP} onpointerup={up} onpointercancel={up} style:--n={N}>
  <span class="tone-base" aria-hidden="true"></span>
  <span class="lens" bind:this={lens} style:translate="{shown * 100}% 0" aria-hidden="true"></span>
  {#each tabs as tab, i (tab)}
    {@const Icon = TAB_ICON[tab]}
    <button class="tab" class:on={shown === i} aria-current={ui.tab === tab ? 'page' : undefined} aria-label={labels[i]} onclick={() => pick(i)}>
      <span class="ic">
        <Icon size={24} strokeWidth={2} />
        {#if dot[i]}<i class="dot"></i>{/if}
      </span>
    </button>
  {/each}
</nav>
<!-- the map beside the tabs, under the thumb on every screen (the button at the top of Today was hard
     to find); a round glass button of its own, like iOS 26's search, so the tabs keep their width -->
<button class="mapb glass glass-pill" class:mini={ui.navMini} aria-label={t('map.open')} use:glass={{ bloom: true }}
        onpointerdown={warm} onclick={openMap}>
  <span class="tone-base" aria-hidden="true"></span>
  <MapIcon size={24} strokeWidth={2} />
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
    box-shadow: 0 12px 32px -10px rgba(0, 0, 0, 0.55);
    transition: height var(--t-base) var(--ease), width var(--t-base) var(--ease);
  }
  .nav { width: min(360px, calc(100% - 68px)); padding: 4px; display: flex; }
  .mapb { width: 60px; display: grid; place-items: center; color: var(--text); }
  .mapb > :global(svg) { position: relative; }
  .mapb:active { transform: scale(0.94); }
  /* an edge all the way round, but lit like glass, not drawn (the even bright outline looked fake): the shared rim's
     bright arc and its reflection over a faint edge, the colour fringes (the owner keeps them: they make the glass) */
  .nav::after, .mapb::after {
    background:
      radial-gradient(ellipse 46% 140% at var(--hx) 0%, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.35) 40%, transparent 72%),
      radial-gradient(ellipse 36% 120% at var(--ox) 100%, rgba(255, 255, 255, 0.45), transparent 70%),
      linear-gradient(90deg, rgba(255, 120, 200, 0.4), transparent 18%, transparent 82%, rgba(90, 190, 255, 0.45)),
      rgba(255, 255, 255, 0.16);
  }
  .nav > .tone-base, .mapb > .tone-base { background: var(--dock); }
  /* the lens: a soft rounded rect behind the active tab (--text at 8 %: seen on the near-white light bar too), moved by
     `translate` so the jelly's `transform` squashes it on the way */
  .lens {
    position: absolute; top: 4px; bottom: 4px; left: 4px; width: calc((100% - 8px) / var(--n)); border-radius: var(--r-full); background: var(--lens);
    transition: translate 380ms var(--ease-spring);
  }
  .tab {
    position: relative; flex: 1 1 0; min-width: 0; padding: 0 2px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
    color: var(--dock-ink); border-radius: var(--r-full);
    transition: color var(--t-base) var(--ease), transform 350ms cubic-bezier(.3, 1.6, .5, 1);
  }
  .tab:active { transform: scale(0.94); transition-duration: var(--t-base), 80ms; }
  .tab.on { color: var(--text); }
  .ic { position: relative; display: inline-flex; flex: none; transition: transform 380ms var(--ease-spring); }
  .dot { position: absolute; top: -1px; right: -3px; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); }
  /* scrolling down: the bar shrinks to a slimmer pill, the map button with it */
  .nav.mini { height: 50px; width: min(250px, calc(100% - 100px)); }
  .mapb.mini { width: 50px; height: 50px; }
</style>
