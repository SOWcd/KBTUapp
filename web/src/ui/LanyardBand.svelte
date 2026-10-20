<script lang="ts">
  // A club's own art on its lanyard (owner, Oct 20, drafts in KBTUapp-OLD/design/lanyards). `wide`: the profile's
  // card keeps its size (owner: "the old size was ideal"), so the art is the card's background: the symbol big on the
  // right, the pom-poms or the ball beside the QR; else a band on top of the full-screen badge, the art in the middle.
  // Art: the panther and the Knights emblem cut from the clubs' logos; Knights' ball is three sports in one (they play
  // basketball, football and volleyball: a student's idea from their tryout poster, Oct 20), white line art like the emblem.
  import type { Look } from '../lib/awards';
  import panther from '../assets/lanyards/panther.webp';
  import knights from '../assets/lanyards/knights.webp';
  import cheerWide from '../assets/lanyards/cheer-wide.svg?url';
  import cheerTall from '../assets/lanyards/cheer-tall.svg?url';
  import ball from '../assets/lanyards/knights-ball.svg?url';

  let { look, wide = false }: { look: Look; wide?: boolean } = $props();
</script>

<div class="band {look}" class:wide aria-hidden="true">
  {#if look === 'cheer'}
    <img class="dec" src={wide ? cheerWide : cheerTall} alt="" /><img class="art" src={panther} alt="" />
  {:else if look === 'knights'}
    <svg class="dec" viewBox="0 0 340 112" preserveAspectRatio="xMidYMid slice"><g fill="none" stroke="#fff" stroke-opacity=".16" stroke-width="2">
      <path d="M-10 8H350" /><circle cx="170" cy="8" r="34" /><path d="M120 112V64H220V112" /><path d="M150 64A20 20 0 0 1 190 64" /><path d="M40 112A130 130 0 0 1 300 112" /></g></svg>
    <img class="ball" src={ball} alt="" /><img class="art" src={knights} alt="" />
  {/if}
</div>

<style>
  .band { position: relative; overflow: hidden; height: 124px; color: #fff; }
  .band.wide { position: absolute; inset: 0; height: auto; }
  img { position: absolute; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  .dec { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; }

  /* Cheerleading: rays behind the panther, gold and pink pom-poms, confetti */
  .cheer { background: repeating-conic-gradient(from 0deg at var(--c, 50% 78%), rgba(255, 255, 255, 0.06) 0 5deg, transparent 5deg 13deg),
    radial-gradient(circle at var(--c, 50% 78%), #5560C2, #2E3258 48%, #14162E); }
  .cheer.wide { --c: 88% 100%; }
  .cheer .art { left: 50%; bottom: -12px; height: 128px; transform: translateX(-50%); }
  .band.wide .art { left: auto; right: -16px; bottom: -30px; height: 168px; transform: none; opacity: 0.22; }
  .band.knights.wide .art { right: -26px; bottom: -18px; height: 150px; }

  /* Knights: royal blue, speed stripes, the court's lines, the emblem */
  .knights { background: repeating-linear-gradient(115deg, rgba(255, 255, 255, 0.05) 0 10px, transparent 10px 26px), linear-gradient(150deg, #3A7BEA, #1C4C94 55%, #0D2A63); }
  .knights .art { left: 50%; top: 10px; height: 112px; transform: translateX(-50%); }
  .ball { right: -14px; bottom: -20px; width: 88px; opacity: 0.9; }
  .wide .ball { right: 26px; bottom: 47px; width: 40px; } /* just above the strip */

</style>
