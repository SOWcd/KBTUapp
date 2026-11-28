<script lang="ts">
  // The campus map's top row (CampusMap.svelte holds it in its .side row): the list of maps, the floors' rail with
  // its glass knob, and the light/dark switch. The rail's gestures are the map's (floorSwipe.ts): it hands over the
  // listeners (swipeable), the knob's place (kp) and whether the last touch was a drag (swiped).
  import Sun from '@lucide/svelte/icons/sun';
  import Moon from '@lucide/svelte/icons/moon';
  import Layers from '@lucide/svelte/icons/layers';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { glass } from '../../ui/glass';
  import type { Theme } from '../../lib/state/theme.svelte';
  import type { Ver } from '../../lib/mapgl';
  import { floorName } from './mapFind';

  let { menu = $bindable(), knob = $bindable(), onWay, ver, vers, onver, floors, routeFloors, cur, kp, dragging, swipeable, swiped, onpick, look, onflip }: {
    menu: boolean; knob: HTMLSpanElement | undefined; onWay: boolean; ver: Ver; vers: Ver[]; onver: (v: Ver) => void;
    floors: number[]; routeFloors: Set<number>; cur: number; kp: number; dragging: boolean;
    swipeable: (el: HTMLElement) => { destroy: () => void }; swiped: () => boolean; onpick: (n: number) => void;
    look: Theme; onflip: (from: Element) => void;
  } = $props();
</script>

<!-- the maps: a tap lists them -->
<div class="maps" class:away={onWay}>
  <button class="rb glass glass-pill" class:on={menu} use:glass onclick={() => { haptic.tap(); menu = !menu; }}
    aria-label={t('map.maps')} aria-expanded={menu}><Layers size={20} /></button>
  {#if menu}
    <div class="menu glass glass-sheet" use:glass>
      {#each vers as v (v)}<button aria-pressed={ver === v} class:on={ver === v} onclick={() => { menu = false; onver(v); }}>{t(`map.ver.${v}` as 'map.ver.main')}</button>{/each}
    </div>
  {/if}
</div>
<!-- on the way only the look button stays: the floors move into the step card -->
<div class="rail glass glass-pill" class:away={onWay} class:dragging inert={onWay} use:glass use:swipeable role="group" aria-label={t('map.floors')} style:--kp={kp}>
  <!-- the knob: a clear glass lens, the rail's numbers again inside it, magnified around its middle -->
  <span class="knob" bind:this={knob} aria-hidden="true"><span class="mag">{#each [0, 1, 2, 3, 4, 5] as n (n)}<i class:gone={!floors.includes(n)}>{n || t('map.bShort')}</i>{/each}</span></span>
  <!-- all six always there: the old map's missing basement folds away in step with the knob, so the rail narrows
       instead of jumping (owner, Oct 24 video) -->
  {#each [0, 1, 2, 3, 4, 5] as n (n)}{@const gone = !floors.includes(n)}<button aria-pressed={cur === n} class:on={cur === n}
    class:r={routeFloors.has(n)} class:gone tabindex={gone ? -1 : undefined} aria-hidden={gone || undefined} onclick={() => { if (!swiped()) onpick(n); }}
    aria-label={floorName(n)}>{n || t('map.bShort')}</button>{/each}
</div>
<!-- a tap turns the map light or dark at once (the menu it opened looked foreign and lagged) -->
<button class="rb glass glass-pill" use:glass onclick={(e) => onflip(e.currentTarget)} aria-label={t('map.theme')}>
  {#if look === 'dark'}<Moon size={20} />{:else}<Sun size={20} />{/if}</button>

<style>
  .rail { touch-action: none; }
  .rb { position: relative; flex: none; width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; color: var(--text); transition: transform 0.45s var(--ease-bounce), opacity 0.3s; }
  .rb.on { background: var(--accent); color: #fff; }
  .rb.away, .maps.away { opacity: 0; pointer-events: none; }
  .maps { position: relative; flex: none; transition: opacity 0.3s; }
  .menu { position: absolute; left: 0; top: 54px; min-width: 190px; padding: 6px; border-radius: 22px; display: grid; gap: 2px; }
  .menu button { text-align: left; padding: 11px 14px; border-radius: 16px; font: inherit; font-weight: 600; color: var(--text); }
  .menu button.on { background: var(--accent); color: #fff; }
  .rb:active { transform: scale(0.92); transition-duration: 80ms; }
  /* a floor button shrinks on a narrow phone so the row fits (two 46px buttons, two 10px gaps, 12px sides) */
  .rail { --fb: min(42px, calc((100vw - 144px) / 6)); position: relative; display: flex; padding: 4px; border-radius: 26px; transition: opacity 0.3s, transform 0.5s var(--ease-spring), --kp 420ms var(--ease-spring); }
  .rail.dragging { transition: opacity 0.3s, transform 0.5s var(--ease-spring), --kp 0s; }
  .rail.away { opacity: 0; transform: translateY(-30px); pointer-events: none; }
  /* the knob's place: one registered number, so its spring moves the lens and the magnified copy inside in one step */
  @property --kp { syntax: '<number>'; inherits: true; initial-value: 0; }
  .rail .knob { position: absolute; z-index: 2; left: 4px; top: 4px; bottom: 4px; width: var(--fb); border-radius: 21px; overflow: hidden; pointer-events: none;
    translate: calc(var(--kp) * var(--fb)) 0;
    /* clear glass: the rail's own colour through it, the plain numbers under it blurred away, a bright rim, a bent edge */
    background: rgba(255, 255, 255, 0.08); backdrop-filter: blur(5px) saturate(1.7); -webkit-backdrop-filter: blur(5px) saturate(1.7);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.5), inset 0 1.5px 1px rgba(255, 255, 255, 0.9), inset 0 -3px 6px rgba(255, 255, 255, 0.16),
      inset 3px 0 6px -3px rgba(120, 170, 255, 0.6), inset -3px 0 6px -3px rgba(255, 140, 190, 0.55), 0 0 0 0.5px rgba(0, 0, 0, 0.08), 0 6px 16px -6px rgba(0, 0, 0, 0.35); }
  .rail .mag { position: absolute; left: 0; top: 0; height: 42px; display: flex;
    transform-origin: calc(var(--kp) * var(--fb) + var(--fb) / 2) 50%; transform: translate3d(calc(var(--kp) * var(--fb) * -1), 0, 0) scale(1.28); }
  .rail .mag i { width: var(--fb); flex: none; display: grid; place-items: center; font: 750 16px/1 var(--font-display); font-style: normal; color: var(--text);
    text-shadow: -0.7px 0 rgba(255, 90, 150, 0.55), 0.7px 0 rgba(90, 170, 255, 0.55); transition: width 0.5s var(--ease-spring); }
  .rail .mag i.gone { width: 0; overflow: hidden; }
  .rail button.on { color: var(--text-2); }
  .rail button { position: relative; width: var(--fb); height: 42px; border-radius: 21px; display: grid; place-items: center; font: 750 16px/1 var(--font-display); color: var(--text-2); transition: color 0.25s, width 0.5s var(--ease-spring), opacity 0.3s; }
  .rail button.gone { width: 0; opacity: 0; overflow: hidden; pointer-events: none; }
  .rail button.r::after { content: ''; position: absolute; bottom: 3px; left: 50%; width: 6px; height: 6px; margin-left: -3px; border-radius: 50%; background: #6e92ff; box-shadow: 0 0 8px #6e92ff; }
</style>
