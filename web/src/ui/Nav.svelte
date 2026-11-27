<script lang="ts">
  // Bottom nav (liquid glass, floats): icons only, the capsule above says the tab's name (a label under
  // each icon only repeated it); the active one in the accent on a raised lighter pill that glides to it on the tab
  // spring, a slight stretch on the way. Equal tabs
  // that stay put, so nothing jumps while a drag previews them. Press and drag along the bar previews tabs; the tab
  // switches on release. Always the slim size; hides under a sheet (and the Feed). The corner: its own round glass
  // button beside it, KRI (the assistant leads anywhere, the map is its first row); the map for a guest
  // and where the assistant is off (BOARD).
  import MapIcon from '@lucide/svelte/icons/map';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import { kriCorner } from '../lib/state/session.svelte';
  import { sheets, openMapFrom, irisFrom } from '../lib/state/sheets';
  import { ui, goTab, type Tab } from '../lib/state/ui.svelte';
  import { haptic } from '../lib/tg';
  import { t } from '../lib/i18n/index.svelte';
  import { glass, refract } from './glass';
  import { TAB_ICON } from './icons';

  // the tabs shown (the forum only where the server opened it), each with its label and dot
  let { tabs, labels, dot = [] }: { tabs: Tab[]; labels: string[]; dot?: boolean[] } = $props();
  const N = $derived(tabs.length);

  let preview = $state<number | null>(null);
  const shown = $derived(preview ?? tabs.indexOf(ui.tab));

  let bar: HTMLElement;
  let lens: HTMLSpanElement;
  // one motion: the pill glides on the tab spring (`translate`, .lens below) and stretches a little on the same clock
  // and curve (the tokens, read once), so the stretch peaks half-way there and is gone as it lands; it grows with the
  // distance. `transform` alone, the origin never moves: compositor only. None on the first paint or under reduced motion
  let was = -1, spring: KeyframeAnimationOptions | undefined;
  $effect(() => {
    const i = shown, d = Math.min(Math.abs(i - was), 3);
    if (was >= 0 && d && lens.animate && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      if (!spring) { const cs = getComputedStyle(lens); spring = { duration: parseFloat(cs.getPropertyValue('--t-tab')), easing: cs.getPropertyValue('--ease-tab').trim() }; }
      const s = 0.03 + 0.03 * d;
      lens.animate({ transform: ['scale(1)', `scale(${1 + s}, ${1 - s * 0.4})`, 'scale(1)'], easing: ['ease-out', 'ease-in-out'] }, spring);
    }
    was = i;
  });
  // lifted: the pill grows into a clear drop while a finger holds it (the active tab pressed, or a drag along the bar),
  // as iOS 26's selection does; it settles back flat on release
  let lift = $state(false);
  let drag: null | { x: number; on: boolean; id: number } = null;
  const idxAt = (x: number) => { const r = bar.getBoundingClientRect(); return Math.max(0, Math.min(N - 1, Math.floor(((x - r.left) / r.width) * N))); };
  function down(e: PointerEvent) { drag = { x: e.clientX, on: false, id: e.pointerId }; lift = idxAt(e.clientX) === shown; }
  function moveP(e: PointerEvent) {
    if (!drag) return;
    if (!drag.on) { if (Math.abs(e.clientX - drag.x) < 8) return; drag.on = true; lift = true; bar.setPointerCapture(drag.id); }
    const i = idxAt(e.clientX);
    if (i !== preview) { preview = i; haptic.select(); }
  }
  function up() {
    const d = drag; drag = null; lift = false;
    if (d?.on && preview != null) { const i = preview; preview = null; goTab(tabs[i]); }
    else preview = null;
  }
  // the button gives under the finger and springs back as the map (CampusMap's iris) or KRI grows out of it
  const give = (b: HTMLElement) => b.animate([{ transform: 'scale(1)' }, { transform: 'scale(0.84)', offset: 0.35 }, { transform: 'scale(1.06)', offset: 0.75 }, { transform: 'scale(1)' }], { duration: 320, easing: 'ease-out' });
  function openMap(e: MouseEvent) { give(e.currentTarget as HTMLElement); openMapFrom(e); }
  // the chunk on the press, not the click: by the release it has been loading for the whole press
  const kri = $derived(kriCorner());
  const warm = () => { void (kri ? import('../screens/assistant/Assistant.svelte') : import('../screens/map/CampusMap.svelte')).catch(() => {}); };
  function corner(e: MouseEvent) {
    if (!kri) return openMap(e);
    irisFrom(e);
    give(e.currentTarget as HTMLElement);
    sheets.assistant();
  }
  function pick(i: number) { if (drag?.on) return; goTab(tabs[i]); }
</script>

<div class="dock">
<nav class="nav glass glass-pill" class:lift bind:this={bar} aria-label={t('nav.label')} use:glass={{ bloom: true }} use:refract
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
<!-- KRI beside the tabs, under the thumb on every screen; a round glass button of its own, like iOS 26's search, so
     the tabs keep their width. Its class stays .mapb: the map's iris closes into it when it opened from here -->
<button class="mapb glass glass-pill" aria-label={kri ? t('as.askAi') : t('map.open')} use:glass={{ bloom: true }} use:refract
        onpointerdown={warm} onclick={corner}>
  <span class="tone-base" aria-hidden="true"></span>
  {#if kri}<Sparkles size={24} strokeWidth={2} />{:else}<MapIcon size={24} strokeWidth={2} />{/if}
</button>
</div>

<style>
  .dock {
    position: absolute; left: 16px; right: 16px; bottom: calc(var(--safe-bottom) + 10px); z-index: var(--z-nav);
    display: flex; justify-content: center; align-items: center; gap: 8px; pointer-events: none;
    transition: transform var(--t-slow) var(--ease-spring), visibility 0s;
  }
  .dock > * { pointer-events: auto; }
  /* the home-screen app: iOS's full home-indicator inset (34 pt) sat the bar ~14 pt above where Telegram puts it (its
     inset is smaller); the same spot in both, still clear of the home indicator (owner's two screenshots, Nov 23) */
  :global(html[data-web]) .dock { bottom: calc(max(0px, var(--safe-bottom) - 14px) + 10px); }
  /* the iPhone app draws the tabs natively (lib/native.ts 'tabs'): the corner button alone, at the right above that bar */
  :global(html[data-ntabs]) .nav { display: none; }
  :global(html[data-ntabs]) .dock { justify-content: flex-end; bottom: calc(var(--safe-bottom) + var(--nav-h) + 10px); }
  /* gone once it has slid away: off screen its two backdrop filters were still composited under every sheet and the
     map (iOS has a budget for them, the map's glass drew without its backdrop once it ran short); back at once */
  :global(html[data-sheet]) .dock { transform: translateY(calc(100% + 40px)); visibility: hidden;
    transition: transform var(--t-slow) var(--ease-spring), visibility 0s var(--t-slow); }
  .nav, .mapb {
    position: relative; flex: none; height: 54px; border-radius: var(--r-full); touch-action: none; overflow: hidden;
    /* the capsule's clear glass (on the big bar the dark frosted body read as plastic) */
    /* calm (what scrolls under it must not smear through crookedly): a stronger blur, less
       saturation; still the one backdrop filter, the rim and glow below are plain paint */
    -webkit-backdrop-filter: blur(20px) saturate(160%) brightness(1.04);
    backdrop-filter: var(--refract, blur(20px) saturate(160%) brightness(1.04));
    background: none;
    box-shadow: 0 12px 32px -10px rgba(0, 0, 0, 0.55);
  }
  .nav { width: min(250px, calc(100% - 100px)); padding: 4px; display: flex; }
  .mapb { width: 54px; display: grid; place-items: center; color: var(--text); }
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
  /* the lens: a raised glass pill behind the active tab (lighter than the bar in both themes, a soft shadow under it).
     Three properties, one each, so they compose on the compositor: `translate` slides it on the tab spring (the pages
     crossfade on the same tokens, App's .tab), `scale` is the lift, `transform` the stretch on the way (the script) */
  .lens {
    position: absolute; top: 4px; bottom: 4px; left: 4px; width: calc((100% - 8px) / var(--n)); border-radius: var(--r-full);
    /* a convex body: lighter at the top, like the bar itself */
    background: linear-gradient(var(--lens-top), transparent 70%), var(--lens);
    box-shadow: var(--lens-shadow);
    transition: translate var(--t-tab) var(--ease-tab), scale 420ms var(--ease-bounce), background-color var(--t-base) var(--ease), box-shadow var(--t-base) var(--ease);
  }
  /* its own rim, lit from the same side as the bar's (the bar's --hx/--ox follow the tilt) */
  .lens::after {
    content: ''; position: absolute; inset: 0; padding: 1px; border-radius: inherit; pointer-events: none;
    background:
      radial-gradient(ellipse 60% 150% at var(--hx) 0%, var(--lens-rim), transparent 72%),
      radial-gradient(ellipse 50% 140% at var(--ox) 100%, var(--lens-rim-low), transparent 72%);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
  }
  /* held: a clear drop that rises off the bar; the icon under it magnified */
  .nav.lift .lens { scale: 1.07 1.1; background-color: var(--lens-lift); box-shadow: var(--lens-lift-shadow); transition-duration: var(--t-tab), 260ms, var(--t-base), var(--t-base); }
  .nav.lift .tab.on .ic { scale: 1.12; }
  .tab {
    position: relative; flex: 1 1 0; min-width: 0; padding: 0 2px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
    color: var(--dock-ink); border-radius: var(--r-full);
    transition: color var(--t-base) var(--ease), transform 350ms cubic-bezier(.3, 1.6, .5, 1);
  }
  .tab:active { transform: scale(0.94); transition-duration: var(--t-base), 80ms; }
  .tab.on { color: var(--accent-text); }
  .ic { position: relative; display: inline-flex; flex: none; transition: transform 380ms var(--ease-spring), scale 420ms var(--ease-bounce); }
  .dot { position: absolute; top: -1px; right: -3px; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); }
</style>
