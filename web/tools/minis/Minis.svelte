<script lang="ts">
  // Each lanyard's card art shrunk to the picker's swatch, exactly as SettingsList drew it live: LanyardBand wide in its
  // look's colours, still (no animation, no tilt), scaled 340 px -> 74 into the swatch's 74 x 48 card
  import LanyardBand from '../../src/ui/LanyardBand.svelte';
  import { STRAP, banded, lookVars, type Look } from '../../src/lib/awards';
  const looks = (Object.keys(STRAP) as Look[]).filter(banded);
</script>

{#each looks as l (l)}<div class="cell" data-look={l} style={lookVars(l)}><span class="mini"><LanyardBand look={l} wide /></span></div>{/each}

<style>
  :global(html), :global(body) { background: transparent !important; }
  .cell { position: relative; width: 74px; height: 48px; overflow: hidden; margin: 4px; }
  .mini { position: absolute; left: 0; top: 0; width: 340px; height: 221px; transform: scale(0.2176); transform-origin: 0 0; pointer-events: none; --gx: 0; --gy: 0; }
  .mini :global(*) { animation: none !important; }
  .mini :global(.z) { will-change: auto; }
</style>
