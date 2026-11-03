<script lang="ts">
  // A pin (awards plan, Nov 3): a one-time award for a moment, an upright enamel shield in a thin metal frame, so it
  // never reads as a medal (round, levels) or a status (the seal by the name). Enamel over an engine-turned ground (zn-enamel),
  // one glyph (struck in the frame's metal, public/medals/zn-<glyph>-<metal>, or an event's emoji), the year small from 64 px. Layered like the medals: the glyph floats with
  // the tilt (base.css .z) between the enamel and the still frame.
  import Emoji from './Emoji.svelte';
  import { SHIELD } from '../lib/awards';
  let { color, emoji = '', glyph = '', metal = 'g', year, off = false, hidden = false, size = 58 }:
    { color: string; emoji?: string; glyph?: string; metal?: 'g' | 's' | 'r'; year?: number; off?: boolean; hidden?: boolean; size?: number } = $props();
</script>

<span class="pin {metal}" class:off style="width:{size}px;height:{size}px">
  <svg viewBox="0 0 512 512" aria-hidden="true"><path d={SHIELD} fill={color} /></svg>
  <img src="medals/zn-enamel.svg" alt="" draggable="false" />
  {#if hidden}<span class="q" style:font-size="{Math.round(size * 0.4)}px">?</span>
  {:else if glyph}<img class="z" style:--z={(size * 0.03).toFixed(1)} src={`medals/zn-${glyph}-${metal}.svg`} alt="" draggable="false" />
  {:else}<span class="glyph z" style:--z={(size * 0.03).toFixed(1)}><Emoji name={emoji} size={Math.round(size * 0.4)} /></span>{/if}
  <img src={`medals/zn-frame-${metal}.svg`} alt="" draggable="false" />
  {#if year && size >= 64 && !hidden}<span class="yr num" style:font-size="{Math.max(8, Math.round(size * 0.075))}px">{year}</span>{/if}
</span>

<style>
  .pin { position: relative; flex: none; display: inline-flex; filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.3)); }
  .pin > :global(*) { position: absolute; inset: 0; width: 100%; height: 100%; }
  .glyph { display: flex; align-items: center; justify-content: center; padding-bottom: 14%; } /* clear of the year */
  .q { display: flex; align-items: center; justify-content: center; padding-bottom: 6%; font-weight: 800; color: rgba(255, 255, 255, 0.7); }
  /* the year on the enamel above the point, in the frame's metal */
  .yr { top: auto; bottom: 17%; height: auto; text-align: center; font-weight: 800; letter-spacing: 0.06em; line-height: 1; }
  .g .yr { color: rgb(255, 222, 130); }
  .s .yr { color: rgb(230, 236, 248); }
  .r .yr { color: rgb(255, 214, 196); }
  .off { filter: grayscale(1); opacity: 0.38; }
</style>
