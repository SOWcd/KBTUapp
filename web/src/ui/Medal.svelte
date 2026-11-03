<script lang="ts">
  // An achievement's art (awards plan, Nov 3): a medal, or a pin (one time: ui/Pin, a shield). A medal is round, drawn
  // in layers (lib/awards layersOf): the field, the picture and its near part float with the tilt (base.css .z, the
  // glass's --gx/--gy from above) under the still rim, whose metal is the level; from 96 px it hangs on a ribbon of that
  // metal, from 160 px (the award card, the unlock) its name is engraved round the band, as on the owner's coins, and the
  // level's numeral sits on the rim. The 2026 initiation's coins stay the owner's drawn pictures (isCoin). Iridescence
  // lives inside one object, never smeared over text (owner's taste).
  import type { Achievement } from '../lib/api';
  import Emoji from './Emoji.svelte';
  import Pin from './Pin.svelte';
  import { ZNAKI, artOf, isCoin, isMedal, layersOf, legendOf, metalLetter, tierLabel, yearOf } from '../lib/awards';
  let { a, size = 64 }: { a: Achievement; size?: number } = $props();

  const hidden = $derived(a.secret && a.level === 0);
  const medal = $derived(isMedal(a));
  const zn = $derived(ZNAKI[a.emoji]);
  const layers = $derived(layersOf(artOf(a)));
  const legend = $derived(size >= 160 && a.level > 0 ? legendOf(artOf(a)) : null);
</script>

{#if isCoin(a)}<span class="medal pic" class:none={a.level === 0} style="width:{size}px;height:{size}px"><img src={`emoji/${a.emoji}.webp`} srcset={`emoji/sm/${a.emoji}.webp 192w, emoji/${a.emoji}.webp 512w`} sizes="{size}px" alt="" width={size} height={size} decoding="async" draggable="false" /></span>
{:else if !medal}<Pin color={zn?.field ?? 'rgb(47, 91, 234)'} glyph={zn?.glyph} emoji={a.emoji} metal={zn?.metal} year={a.level ? yearOf(a.at, zn?.year) : undefined} off={a.level === 0} {hidden} {size} />
{:else if layers}<span class="medal lay" class:none={a.level === 0} style="width:{size}px;height:{size}px">
  {#if size >= 96}<img class="rib" src={`medals/ribbon-${metalLetter(a)}.svg`} alt="" draggable="false" />{/if}
  {#each layers as [n, z] (n)}<img class:z={z !== 0} style:--z={z ? (z * size * 0.03).toFixed(1) : null} src={`medals/${n}.svg`} alt="" draggable="false" />{/each}
  {#if legend}<img src={`medals/${legend}.svg`} alt="" draggable="false" />{/if}
  {#if size >= 160 && a.level > 0 && a.levels.length > 1}<span class="lv {metalLetter(a)}" style:font-size="{Math.round(size * 0.075)}px">{tierLabel(a.level, a.levels.length)}</span>{/if}
</span>
{:else}<span class="medal emo" class:none={a.level === 0} style="width:{size}px;height:{size}px">
  {#if hidden}<span class="q" style="font-size:{Math.round(size * 0.4)}px">?</span>{:else}<Emoji name={a.emoji} size={Math.round(size * 0.58)} />{/if}
</span>{/if}

<style>
  .medal { position: relative; flex: none; border-radius: 50%; display: inline-flex; }
  .lay img { position: absolute; inset: 0; width: 100%; height: 100%; }
  .lay:not(.none) { box-shadow: 0 4px 10px -2px rgba(0, 0, 0, 0.45); }
  .lay.none { filter: grayscale(1); opacity: 0.38; }
  /* the ribbon's two tails behind the disc, below it (its file is 512 x 640: the disc's box and a quarter more) */
  .lay .rib { height: 125%; }
  /* the level on a small dark plate over the rim's foot, in the metal's colour */
  .lv { position: absolute; left: 50%; bottom: 1.5%; translate: -50% 0; padding: 2px 9px; border-radius: var(--r-full); background: rgba(10, 8, 20, 0.72);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.25); font-weight: 800; letter-spacing: 0.08em; line-height: 1.3; }
  .lv.b { color: rgb(255, 205, 160); }
  .lv.s { color: rgb(232, 238, 250); }
  .lv.g, .lv.l { color: rgb(255, 222, 130); }
  /* the owner's drawn coin: the picture is the whole medal; its shadow is the round box's, not a drop-shadow filter on
     the image (WebKit draws a filtered image through a square buffer: a light square round the coin, sometimes) */
  .pic img { width: 100%; height: 100%; object-fit: contain; }
  .pic:not(.none) { box-shadow: 0 4px 8px rgba(0, 0, 0, 0.45); }
  .pic.none img { filter: grayscale(1); opacity: 0.38; }
  /* a future medal not drawn yet: its emoji on a plain disc */
  .emo { align-items: center; justify-content: center; background: radial-gradient(70% 70% at 35% 25%, var(--surface-3), var(--surface)); box-shadow: inset 0 0 0 3px var(--line-2); }
  .emo.none :global(img) { filter: grayscale(1); opacity: 0.38; }
  .q { font-weight: 800; color: var(--text-3); }
</style>
