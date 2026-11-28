<script lang="ts">
  // The hero's picture (List.svelte): the event's cover whole, or with none the club's colour as one calm field with the
  // event's 3D mark in its middle. Its own, not ui/Poster: the first card's cover is the screen's biggest picture, so it
  // is asked for at once and first (eager, fetchpriority high); the cards a swipe away load lazily.
  import Emoji from '../../ui/Emoji.svelte';
  import { focusPos } from '../../lib/photo';

  type Pic = { url: string; thumb: string; focus?: [number, number] | null };
  let { pic, emoji, color, first = false }: { pic: Pic | null; emoji: string | null; color: string; first?: boolean } = $props();
</script>

<!-- .poster: the event's sheet opens out of this box (sheets.event's second argument) -->
<div class="poster" class:mesh={!pic} style:--c={color}>
  {#if pic}
    <!-- the thumb the lists already hold, under the big one while it comes -->
    <img draggable="false" src={pic.thumb} alt="" decoding="async" style:object-position={focusPos(pic)} />
    <img draggable="false" src={pic.url} alt="" decoding="async" loading={first ? 'eager' : 'lazy'} fetchpriority={first ? 'high' : 'auto'} style:object-position={focusPos(pic)} />
    <span class="scrim"></span>
  {:else}
    <span class="mark"><Emoji name={emoji ?? 'sparkles_3d'} size={168} /></span>
  {/if}
</div>

<style>
  .poster { position: absolute; inset: 0; overflow: hidden; background: var(--c); }
  img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  /* no cover: a poster drawn from what the event has, the way a featured card with no artwork is made: one calm field of
     the club's colour, a little lifted at the top and deep at the foot (no pools of light, no mesh), the event's 3D
     mark standing in its middle above the words; a fine grain over it so the wide field of one colour doesn't band */
  .mesh { background: linear-gradient(rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0) 30%, rgba(0, 0, 0, 0.5)), var(--c); }
  .mesh::after { content: ''; position: absolute; inset: 0; opacity: 0.14; mix-blend-mode: overlay;
    background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E"); }
  /* under the words (the card's lower part): a clean dark gradient over the cover, clear above. It holds white words on
     a bright, a dark and a busy poster alike (a blurred copy of the cover there turned real bright posters to mud) */
  .scrim { position: absolute; inset: 0; background: var(--media-scrim); }
  /* sized from the card's height, so it clears the words on a short card as on a tall one */
  .mark { position: absolute; left: 50%; top: 10%; height: 38%; display: flex; transform: translateX(-50%); filter: drop-shadow(0 18px 18px rgba(0, 0, 0, 0.3)); }
  .mark :global(.emoji) { width: auto; height: 100%; }
</style>
