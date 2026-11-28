<script lang="ts">
  // The hero's picture (List.svelte): the event's cover whole, or with none the club's colour as a soft mesh with the
  // event's 3D mark off-centre. Its own, not ui/Poster: the first card's cover is the screen's biggest picture, so it
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
  /* no cover: light from the top left, a second pool low at the right, the far corner deep; a fine grain over it so
     the wide field of one colour doesn't band. The mark high at the right, tilted, clear of the words */
  .mesh { background:
    radial-gradient(70% 55% at 12% 6%, rgba(255, 255, 255, 0.34), transparent 70%),
    radial-gradient(60% 50% at 96% 64%, rgba(255, 255, 255, 0.16), transparent 72%),
    radial-gradient(90% 70% at 20% 100%, rgba(0, 0, 0, 0.5), transparent 70%),
    linear-gradient(160deg, transparent 30%, rgba(0, 0, 0, 0.34)),
    var(--c); }
  .mesh::after { content: ''; position: absolute; inset: 0; opacity: 0.14; mix-blend-mode: overlay;
    background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E"); }
  /* under the words (the card's lower part): a clean dark gradient over the cover, clear above. It holds white words on
     a bright, a dark and a busy poster alike (a blurred copy of the cover there turned real bright posters to mud) */
  .scrim { position: absolute; inset: 0; background: linear-gradient(to top, rgba(0, 0, 0, 0.94), rgba(0, 0, 0, 0.86) 30%, rgba(0, 0, 0, 0.5) 50%, rgba(0, 0, 0, 0) 70%); }
  .mark { position: absolute; right: 7%; top: 9%; display: flex; transform: rotate(8deg); filter: drop-shadow(0 16px 20px rgba(0, 0, 0, 0.3)); }
</style>
