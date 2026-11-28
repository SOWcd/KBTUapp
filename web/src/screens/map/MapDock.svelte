<script lang="ts">
  // The campus map's bottom (CampusMap.svelte): the credit line, and under the thumb the way out small on the left,
  // the search, and the map's own round button on the right (a tap there closes the map, as the nav's opened it; the
  // iris closes into it, mapIris.ts finds it as .shut). Both step aside while a card, the keypad or a route is up.
  import Search from '@lucide/svelte/icons/search';
  import MapIcon from '@lucide/svelte/icons/map';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import { t } from '../../lib/i18n/index.svelte';
  import { glass } from '../../ui/glass';

  let { away, busy, note, onexit, onfind, onclose }: {
    away: boolean; busy: boolean; note: string; onexit: () => void; onfind: () => void; onclose: () => void;
  } = $props();
</script>

<!-- the credit, and the old plan for who wants it, under the map as before the redo -->
<p class="note" class:away={away}>{note}</p>
<!-- the bottom, under the thumb: the way out small on the left, the search, and on the right
     the app's own map button, lit: a tap there closes the map, as the button opened it -->
<div class="dock" class:away={away} inert={away}>
  <button class="exit glass glass-pill" use:glass disabled={busy} aria-busy={busy} onclick={onexit} aria-label={t('route.out')}><DoorOpen size={22} /></button>
  <button class="bar glass glass-pill" use:glass onclick={onfind}><Search size={20} /><span class="ellipsis">{t('map.find')}</span></button>
  <button class="shut glass glass-pill" use:glass onclick={onclose} aria-label={t('common.close')}><MapIcon size={22} strokeWidth={1.9} /></button>
</div>

<style>
  .note { position: absolute; z-index: 1; left: 0; right: 0; bottom: calc(var(--safe-bottom) + 84px); margin: 0; text-align: center; font: 550 12px/1.3 var(--font-text); color: var(--text-3);
    transition: opacity 0.25s; }
  .note.away { opacity: 0; pointer-events: none; }
  /* the bottom: the search bar and the exit */
  /* where the app's nav and its map button stand (Nav.svelte), so the closing circle ends on this one */
  .dock { position: absolute; z-index: 2; left: 16px; right: 16px; bottom: calc(var(--safe-bottom) + 10px); display: flex; align-items: center; gap: 8px; transition: transform 0.55s var(--ease-spring), opacity 0.25s; }
  .dock.away { transform: translateY(130%); opacity: 0; pointer-events: none; }
  .bar { position: relative; flex: 1; min-width: 0; height: 60px; border-radius: 30px; display: flex; align-items: center; gap: 10px; padding: 0 16px; font: 600 16px/1 var(--font-text); color: var(--text-2); }
  .bar :global(svg) { color: var(--text); flex: none; }
  .exit { position: relative; width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; color: var(--success); flex: none; }
  /* the same neutral glass as the other map controls (the accent-lit one read oddly blue: owner, Nov 26) */
  .shut { position: relative; width: 54px; height: 54px; border-radius: 50%; display: grid; place-items: center; flex: none; color: var(--text); }
  .bar, .exit, .shut { transition: transform 0.45s var(--ease-bounce); }
  .bar:active, .exit:active, .shut:active { transform: scale(0.95); transition-duration: 80ms; }
  .exit:disabled { opacity: 0.65; }
</style>
