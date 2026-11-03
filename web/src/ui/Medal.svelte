<script lang="ts">
  // Achievement medal. The rim tells the tier: bronze / silver / gold, and Legend is iridescent —
  // iridescence lives inside one object, never smeared over text (owner's taste).
  import type { Achievement } from '../lib/api';
  import Emoji from './Emoji.svelte';
  import { METALS, artOf, layersOf, metalOf } from '../lib/awards';
  let { a, size = 64 }: { a: Achievement; size?: number } = $props();

  const multi = $derived(a.levels.length > 1);
  const tier = $derived(a.level === 0 ? 'none' : !multi ? 'one' : METALS[metalOf(a.level, a.levels.length)]);
  const hidden = $derived(a.secret && a.level === 0);
  // a drawn medal of its own (the 2026 initiation's, First 500; owner Nov 1): the picture is the whole medal, no rim or disc
  const art = $derived(artOf(a));
  const drawn = $derived(art.startsWith('medal_'));
  // a layered one (SVG, crisp at any size): the field, the art and its near part float with the tilt (base.css .z, the
  // glass's --gx/--gy from above) under the still rim
  const layers = $derived(layersOf(art));
</script>

{#if layers}<span class="medal drawn lay" class:none={a.level === 0} style="width:{size}px;height:{size}px">{#each layers as [n, z] (n)}<img class:z={z !== 0} style:--z={z ? (z * size * 0.03).toFixed(1) : null} src={`medals/${n}.svg`} alt="" draggable="false" />{/each}</span>
{:else if drawn}<span class="medal drawn pic" class:none={a.level === 0} style="width:{size}px;height:{size}px"><img src={`emoji/${art}.webp`} alt="" width={size} height={size} decoding="async" draggable="false" /></span>{:else}
<span class="medal {tier}" style="width:{size}px;height:{size}px">
  <span class="disc">
    {#if hidden}<span class="q" style="font-size:{Math.round(size * 0.4)}px">?</span>
    {:else}<Emoji name={a.emoji} size={Math.round(size * 0.58)} />{/if}
  </span>
</span>{/if}

<style>
  .medal { position: relative; flex: none; border-radius: 50%; padding: 3px; display: inline-flex; }
  .disc { width: 100%; height: 100%; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: radial-gradient(70% 70% at 35% 25%, var(--surface-3), var(--surface)); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12); }
  .q { font-weight: 800; color: var(--text-3); }
  .none { background: var(--surface-2); }
  .none .disc :global(img) { filter: grayscale(1); opacity: 0.38; }
  .one { background: var(--grad-accent); }
  .bronze { background: linear-gradient(145deg, #F3BE93, #A5622D 60%, #E0A06A); }
  .silver { background: linear-gradient(145deg, #FFFFFF, #9AA6BF 60%, #E6ECF8); }
  .gold { background: linear-gradient(145deg, #FFE9A8, #D99A16 55%, #FFD45E); }
  .legend { background: conic-gradient(from 210deg, #FF6BD6, #7C4DFF, #35D0FF, #2FD3A0, #FFD23F, #FF6BD6); animation: spin 9s linear infinite; }
  .legend .disc { animation: spin 9s linear infinite reverse; }
  :global(html.lowfx) .legend, :global(html.lowfx) .legend .disc { animation: none; } /* power saving */
  .drawn, .medal.drawn:not(.none) { padding: 0; background: none; box-shadow: none; }
  .drawn img { width: 100%; height: 100%; object-fit: contain; }
  /* a picture medal is a round coin: its shadow is the round box's, not a drop-shadow filter on the image (WebKit draws
     a filtered image through a square buffer: a light square round the coin on the light theme's shelf, sometimes) */
  .medal.pic:not(.none) { box-shadow: 0 4px 8px rgba(0, 0, 0, 0.45); }
  .drawn.none img { filter: grayscale(1); opacity: 0.38; }
  .lay { border-radius: 50%; }
  .lay img { position: absolute; inset: 0; filter: none; }
  .medal.lay:not(.none) { box-shadow: 0 4px 10px -2px rgba(0, 0, 0, 0.45); }
  .lay.none { filter: grayscale(1); opacity: 0.38; }
  .lay.none img { filter: none; opacity: 1; }
  .medal:not(.none) { box-shadow: 0 6px 18px -8px rgba(0, 0, 0, 0.6); }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
