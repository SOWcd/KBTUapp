<script lang="ts">
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Search from '@lucide/svelte/icons/search';
  import X from '@lucide/svelte/icons/x';
  import MapIcon from '@lucide/svelte/icons/map';
  import Play from '@lucide/svelte/icons/play';
  import Images from '@lucide/svelte/icons/images';
  import Newspaper from '@lucide/svelte/icons/newspaper';
  import { t } from '../lib/i18n/index.svelte';
  import { flushSync, tick } from 'svelte';
  import { data } from '../lib/state/data.svelte';
  import { irisFrom, openMapFrom, sheets } from '../lib/state/sheets';
  import { goTab, topAction, ui } from '../lib/state/ui.svelte';
  import { backButton, onAndroid } from '../lib/tg';
  import { backOut, cubicIn } from 'svelte/easing';
  import { calm } from './fold';
  import { glass } from './glass';
  import { tabSearches, type TabSearch } from './PullSearch.svelte';

  // tint: the page on top is tinted (as the capsule's): wherever the side pills go solid they take its colour
  let { back, tint = null }: { back: boolean; tint?: string | null } = $props();

  // Quick launch (owner, Nov 24): the right pill holds the four things students open from anywhere (the Afisha's own
  // shortcuts), two taps from any tab. Closed it shows four dots; they are the tiles themselves, small. A tap drops
  // them out of the pill into a shelf that grows under it (never over the capsule), each dot becoming its tile, and
  // the pill's face turns into an x that closes it (transforms only, nothing mounts on the tap).
  let launching = $state(false), grid = $state<HTMLDivElement>();
  const iris = (go: () => void) => (e: MouseEvent) => { irisFrom(e); go(); };
  const tiles = $derived([
    { icon: MapIcon, label: t('map.open'), go: openMapFrom },
    { icon: Play, label: t('page.feed'), go: iris(() => sheets.feed()), off: !data.events.some((e) => e.status !== 'cancelled') },
    { icon: Images, label: t('gallery.title'), go: iris(() => sheets.gallery()) },
    { icon: Newspaper, label: t('page.news'), go: iris(() => sheets.news()) },
  ]);
  // the map's chunk on the press (the other three are warmed with the app, App.svelte warmPages)
  const warm = () => void import('../screens/map/CampusMap.svelte').catch(() => {});
  const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') launching = false; };
  function unfold() {
    flushSync(() => { launching = true; });
    grid?.querySelector<HTMLElement>('button:not(:disabled)')?.focus({ preventScroll: true });
  }

  // The screen's own action (owner, Nov 27), as an iOS nav bar's trailing item: the screen on top declares it
  // (Overlay.action) the way it names itself in the capsule, and the pill becomes it. The dots fade into the pill's
  // middle and the action's icon turns in; one action to the next crossfades the same way. None: the menu is back.
  const act = $derived(topAction());
  $effect(() => { if (act) launching = false; });
  const turn = (_: Element, { out = false } = {}) => ({ duration: calm() ? 0 : out ? 140 : 380, delay: out ? 0 : 60, easing: out ? cubicIn : backOut,
    css: (k: number) => `opacity: ${k}; transform: rotate(${(1 - k) * (out ? 30 : -30)}deg) scale(${0.55 + 0.45 * k})` });
  function press(e: MouseEvent) {
    if (act) act.run(e);
    else if (launching) launching = false;
    else unfold();
  }

  // The one search of the web app. No Back: the left pill is Search, and a tap stretches it into a field across the whole
  // bar (the capsule and quick launch step aside); it types into the tab's own search (each tab's PullSearch lends its
  // value). Profile has none: the Afisha's. An overlay over the results brings the Back face; the field is back after it.
  let field = $state(false), active = $state.raw<TabSearch | null>(null), tabAt = $state(ui.tab);
  let input = $state<HTMLInputElement>();
  const shown = $derived(field && !back);
  const mine = () => [...tabSearches].find((s) => {
    const tab = s.node?.closest<HTMLElement>('.tab');
    return !tab || tab.classList.contains('on'); // the shown tab (App.svelte), not one away or being drawn unseen
  }) ?? null;

  async function search() {
    if (ui.tab === 'profile') goTab('afisha');
    else if (!mine()) return;
    tabAt = ui.tab;
    flushSync(() => { field = true; });
    input?.focus({ preventScroll: true }); // inside the tap, or iOS shows no keyboard
    await tick();
    active = mine();
    if (!active) { field = false; return; }
    active.node?.closest('.scroll')?.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function shut() {
    if (active) active.value = '';
    active = null;
    field = false;
    input?.blur();
  }

  function keys(e: KeyboardEvent) {
    if (e.key === 'Escape') shut();
    else if (e.key === 'Enter') input?.blur();
  }

  $effect(() => { if (field && ui.tab !== tabAt) shut(); }); // another tab: its own search, not this one's words
  $effect(() => {
    document.documentElement.toggleAttribute('data-search', shown); // the capsule steps aside (ui/Capsule.svelte)
    return () => document.documentElement.removeAttribute('data-search');
  });
</script>

<header class="bar" style:--chrome-tint={tint}>
  <!-- always there (owner, Nov 22): the capsule's glass, a step smaller than it. Its face changes, Search <-> Back: the
       old one leaves a few px towards where it came from, the new one settles in from the other side, the word a beat
       behind its icon. Or it becomes the search field (above). -->
  <div class="glass glass-pill side left" class:back class:field={shown} class:tinted={!!tint} class:flat={onAndroid} use:glass={{ bloom: true }}>
    <span class="tone-base" aria-hidden="true"></span>
    <button class="face" type="button" inert={shown} aria-label={back ? t('web.back') : t('web.search')} onclick={() => (back ? backButton.click() : void search())}>
      <span class="ico" aria-hidden="true"><i class="a"><Search size={15} strokeWidth={2.4} /></i><i class="b"><ChevronLeft size={18} strokeWidth={2.4} /></i></span>
      <span class="txt" aria-hidden="true"><i class="a">{t('web.search')}</i><i class="b">{t('web.back')}</i></span>
    </button>
    <label class="fld" inert={!shown}>
      <Search size={15} strokeWidth={2.4} />
      <input bind:this={input} type="search" enterkeyhint="search" autocomplete="off" placeholder={active?.placeholder ?? t('web.search')}
        aria-label={active?.placeholder ?? t('web.search')} value={active?.value ?? ''} oninput={(e) => { if (active) active.value = e.currentTarget.value; }} onkeydown={keys} />
      <button class="x" type="button" aria-label={t('common.close')} onclick={shut}><X size={15} strokeWidth={2.4} /></button>
    </label>
  </div>
  {#if launching}<div class="catch" role="presentation" onclick={() => (launching = false)}></div>{/if}
  <div class="glass glass-pill shelf" class:open={launching} aria-hidden="true"><span class="tone-base"></span></div>
  <button class="glass glass-pill side more" class:open={launching} class:away={shown} class:tinted={!!tint} class:flat={onAndroid} type="button" inert={shown}
    aria-label={act?.label ?? t('web.menu')} aria-haspopup={act ? undefined : 'menu'} aria-expanded={act ? undefined : launching}
    onpointerdown={act ? undefined : warm} onclick={press} onkeydown={esc} use:glass={{ bloom: true }}>
    <span class="tone-base" aria-hidden="true"></span><X size={17} strokeWidth={2.4} />
    {#if act}{#key act.icon}<span class="act" aria-hidden="true" in:turn|global out:turn|global={{ out: true }}><act.icon size={17} strokeWidth={2.4} /></span>{/key}{/if}
  </button>
  <div class="grid" class:open={launching} class:away={shown} class:hid={!!act} role="menu" tabindex="-1" inert={!launching} bind:this={grid} onkeydown={esc}>
    {#each tiles as x, i (i)}
      {@const Icon = x.icon}
      <button class="tile" type="button" role="menuitem" disabled={x.off} style:--i={i} onclick={(e) => { launching = false; x.go(e); }}>
        <span class="chip"><Icon size={20} strokeWidth={2} /></span>
        <span class="lb">{x.label}</span>
      </button>
    {/each}
  </div>
</header>

<style>
  /* the capsule's own line (its top and 38 px, ui/Capsule.svelte); the pills 34 px on its middle, one width (--pill,
     tokens.css), the capsule the largest thing in the bar, 10 px clear of each */
  .bar { position: absolute; inset: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)) 0 auto; height: 38px;
    z-index: calc(var(--z-sheet) + 7); padding-inline: 12px; display: flex; align-items: center; pointer-events: none; }
  .side { position: relative; flex: none; width: var(--pill); height: 34px; border-radius: var(--r-full); background: none; color: var(--text);
    font: 600 var(--fs-sub)/1 var(--font-text); letter-spacing: -0.005em; pointer-events: auto;
    transition: transform 200ms var(--ease), opacity 180ms var(--ease), width 460ms var(--ease-spring); }
  .side > .tone-base { background: var(--glass-clear); }
  :global(html[data-theme='light'][data-sheet]) .side > .tone-base { background: var(--glass-solid); }
  /* the capsule's twins (ui/Capsule.svelte): no live blur on Android, and solid over a tinted page takes the page's mix */
  .side.flat { -webkit-backdrop-filter: none; backdrop-filter: none; }
  .side.flat > .tone-base { background: var(--glass-solid); }
  :global(html:is(.lowfx, .vt-solid, .glass-wake)) .side.tinted > .tone-base, .side.flat.tinted > .tone-base,
  :global(html[data-theme='light'][data-sheet]) .side.tinted > .tone-base {
    background: linear-gradient(var(--fill), var(--fill)), linear-gradient(var(--tint-veil), var(--tint-veil)), var(--chrome-tint); }
  .side:active { transform: scale(.94); }
  .side :global(svg) { flex: none; }
  .more { position: absolute; right: 12px; top: 2px; display: flex; align-items: center; justify-content: center; }
  .more.away, .grid.away { opacity: 0; transform: translateX(12px) scale(.9); }

  /* quick launch. The shelf waits unseen in the pill's own box and comes down from under it on a spring (a 2% breath
     past its size), 8 px under the bar: the capsule stays whole. Closing is the same gesture back, on one
     curve for the glass and the tiles so they travel as one thing: the glass thins away as it draws up into the pill
     (gone before it is small: no dark box around the dots), the tiles ride home in it, their icons going as they
     shrink, and land as the dots, the x turning out under them. */
  .bar { --spring: var(--ease-spring); }
  @supports (transition-timing-function: linear(0, 1)) {
    .bar { --spring: linear(0, 0.083 4%, 0.26 8%, 0.503 13%, 0.707 18%, 0.875 24%, 0.967 30%, 1.011 37%, 1.02 45%, 1.011 55%, 1.003 67%, 1 80%, 1); }
  }
  .catch { position: fixed; inset: 0; pointer-events: auto; }
  .shelf { position: absolute; right: 12px; top: 2px; width: var(--pill); height: 34px; border-radius: var(--r-xl); opacity: 0; pointer-events: none;
    transition: transform 420ms var(--ease-spring), width 420ms var(--ease-spring), height 420ms var(--ease-spring), opacity 180ms linear; }
  .shelf > .tone-base { background: var(--menu-bg); }
  .shelf.open { width: 192px; height: 172px; transform: translateY(42px); opacity: 1; pointer-events: auto;
    transition: transform 520ms var(--spring), width 520ms var(--spring), height 520ms var(--spring), opacity 120ms var(--ease); }
  /* the pill's face: the dots leave it (they are the tiles, below), an x turns in where they were */
  .more > :global(svg) { opacity: 0; transform: rotate(-90deg) scale(.5); transition: opacity 180ms var(--ease) 80ms, transform 320ms var(--ease) 40ms; }
  .more.open > :global(svg) { opacity: 1; transform: none; transition: opacity 200ms var(--ease) 90ms, transform 460ms var(--spring) 60ms; }
  /* the tiles lie where they stand open, in the shelf's box; closed, each is drawn at an eighth with its chip's middle
     on its dot of the 2 x 2 on the pill (5 px dots, 9 px apart, about the pill's middle) */
  .grid { position: absolute; top: 44px; right: 12px; width: 192px; height: 172px; outline: none; pointer-events: none;
    transition: transform 200ms var(--ease), opacity 180ms var(--ease); }
  .grid.open { pointer-events: auto; }
  /* the screen's action holds the pill: the dots draw into its middle and fade (the pill's centre in the grid's box) */
  .grid.hid { opacity: 0; transform: scale(.6); transform-origin: calc(192px - var(--pill) / 2) -25px;
    transition: transform 220ms var(--ease-in), opacity 140ms var(--ease-in); }
  .act { position: absolute; inset: 0; display: grid; place-items: center; pointer-events: none; }
  .tile { position: absolute; left: 8px; top: 8px; width: 86px; height: 76px; padding-top: 8px; display: flex; flex-direction: column; align-items: center; gap: 6px;
    color: var(--text); transform-origin: 50% 28px; transform: translate(var(--x), var(--y)) scale(.125);
    --x: calc(136.5px - var(--pill) / 2); --y: -65.5px; transition: transform 420ms var(--ease-spring) calc((3 - var(--i)) * 12ms); }
  .tile:nth-child(even) { left: 98px; --x: calc(55.5px - var(--pill) / 2); }
  .tile:nth-child(n + 3) { top: 88px; --y: -136.5px; }
  .open .tile { transform: none; transition: transform 560ms var(--spring) calc(var(--i) * 30ms); }
  .tile:active, .tile:disabled { opacity: 1; }
  .chip { display: flex; align-items: center; justify-content: center; width: 40px; height: 40px; flex: none; border-radius: var(--r-full);
    background: var(--text); transition: background-color 200ms var(--ease) 140ms, transform 200ms var(--ease-bounce); }
  /* a small lens of the panel's own glass (owner: flat grey discs read as old iOS): clear fill, a sheen from the top, the
     lens rim light above and low below */
  .open .chip { background: radial-gradient(120% 90% at 50% 0%, var(--glass-sheen), transparent 60%), var(--glass-clear);
    box-shadow: inset 0 1px 0 var(--lens-rim), inset 0 -1px 0 var(--lens-rim-low), inset 0 0 0 1px var(--lg-rim-base);
    transition-delay: calc(var(--i) * 30ms), 0s; }
  .open .tile:active:not(:disabled) .chip { transform: scale(.9); background: var(--fill); }
  .open .tile:focus-visible { outline: none; }
  .open .tile:focus-visible .chip { box-shadow: 0 0 0 2px var(--accent); }
  .chip :global(svg), .lb { opacity: 0; transition: opacity 80ms var(--ease); }
  .chip :global(svg) { transition-duration: 200ms; }
  .open .chip :global(svg), .open .lb { opacity: 1; transition: opacity 240ms var(--ease) calc(90ms + var(--i) * 30ms); }
  .open .tile:disabled :global(svg), .open .tile:disabled .lb { opacity: .35; }
  .lb { max-width: 100%; font: 500 var(--fs-cap)/1.2 var(--font-text); letter-spacing: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .face { display: flex; align-items: center; justify-content: center; gap: 3px; width: var(--pill); height: 100%; padding-inline: 6px;
    color: inherit; font: inherit; letter-spacing: inherit; transition: opacity 160ms var(--ease); }
  .ico, .txt { display: grid; place-items: center; }
  .txt { overflow: hidden; min-width: 0; }
  /* a face coming in: after the old one has begun to go, the word a beat behind its icon, a soft settle */
  .ico > i, .txt > i { grid-area: 1 / 1; font-style: normal; white-space: nowrap;
    transition: opacity 240ms var(--ease) 70ms, transform 480ms var(--ease-spring) 40ms; }
  .ico > i { display: flex; }
  .txt > i { transition-delay: 110ms, 80ms; }
  /* a face not shown waits a few px to its side (Search to the left of Back), the icon a touch small; going there it is quick */
  .ico > .b, .back .ico > .a, .txt > .b, .back .txt > .a { opacity: 0; transition: opacity 130ms var(--ease-in), transform 220ms var(--ease-in); }
  .ico > .b { transform: translateX(5px) scale(.84); }
  .txt > .b { transform: translateX(9px); }
  .back .ico > .a { transform: translateX(-5px) scale(.84); }
  .back .txt > .a { transform: translateX(-9px); }
  .back .ico > .b, .back .txt > .b { opacity: 1; transform: none; transition: opacity 240ms var(--ease) 70ms, transform 480ms var(--ease-spring) 40ms; }
  .back .txt > .b { transition-delay: 110ms, 80ms; }

  /* the search field: the pill itself, stretched across the bar; its face fades where it stands, the field comes up in it */
  .left.field { width: 100%; }
  .left.field:active { transform: none; }
  .field .face { opacity: 0; }
  .fld { position: absolute; inset: 0; display: flex; align-items: center; gap: 6px; padding: 0 2px 0 11px; opacity: 0;
    transition: opacity 140ms var(--ease); }
  .field .fld { opacity: 1; transition: opacity 260ms var(--ease) 120ms; }
  .fld input { flex: 1; min-width: 0; height: 100%; font: 450 var(--fs-row)/1.2 var(--font-text); letter-spacing: -0.012em; color: var(--text); }
  .fld input::placeholder { color: var(--text-3); }
  .fld input::-webkit-search-cancel-button { display: none; }
  .x { position: relative; display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; flex: none; border-radius: var(--r-full); color: var(--text-2); }
  .x::after { content: ''; position: absolute; inset: -7px; } /* a 44 px target */
  @media (prefers-reduced-motion: reduce) {
    .side, .ico > i, .txt > i, .fld, .shelf, .grid, .tile, .chip, .more > :global(svg), .chip :global(svg), .lb { transition: opacity 120ms linear !important; }
    .ico > i, .txt > i, .more.away, .grid.away, .grid.hid, .more > :global(svg) { transform: none !important; }
  }
</style>
