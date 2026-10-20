<script lang="ts">
  // The top of a lanyard's card (owner, Oct 20, two drafts in KBTUapp-OLD/design/lanyards): each club's own art in full
  // colour, not a faint watermark. `wide`: the profile's horizontal card (art right, wordmark left, the photo overlaps
  // its bottom-left corner); else the full-screen badge's (art in the middle, the strip below names it).
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
    {#if wide}<span class="wm ch">CHEERLEADING<small>KBTU</small></span>{/if}
  {:else if look === 'knights'}
    <svg class="dec" viewBox="0 0 340 112" preserveAspectRatio="xMidYMid slice"><g fill="none" stroke="#fff" stroke-opacity=".16" stroke-width="2">
      <path d="M-10 8H350" /><circle cx="170" cy="8" r="34" /><path d="M120 112V64H220V112" /><path d="M150 64A20 20 0 0 1 190 64" /><path d="M40 112A130 130 0 0 1 300 112" /></g></svg>
    <img class="ball" src={ball} alt="" /><img class="art" src={knights} alt="" />
  {/if}
</div>

<style>
  .band { position: relative; overflow: hidden; height: 124px; color: #fff; }
  .band.wide { height: 84px; } /* owner, Oct 20: the taller card left too much empty space */
  img { position: absolute; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  .dec { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
  .wm { position: absolute; left: 18px; top: 20px; display: flex; flex-direction: column; gap: 5px; white-space: nowrap; text-shadow: 0 2px 10px rgba(0, 0, 0, 0.35); }
  .wm small { font: 800 8.5px/1 var(--font-text); letter-spacing: 0.24em; opacity: 0.92; }

  /* Cheerleading: rays behind the panther, gold and pink pom-poms, confetti */
  .cheer { background: repeating-conic-gradient(from 0deg at var(--c, 50% 78%), rgba(255, 255, 255, 0.06) 0 5deg, transparent 5deg 13deg),
    radial-gradient(circle at var(--c, 50% 78%), #5560C2, #2E3258 48%, #14162E); }
  .cheer.wide { --c: 72% 70%; }
  .cheer .art { left: 50%; bottom: -12px; height: 128px; transform: translateX(-50%); }
  .cheer.wide .art { left: auto; right: 50px; bottom: -8px; height: 90px; transform: none; }
  .ch { font: 700 17px/1 Georgia, 'Times New Roman', serif; letter-spacing: 0.14em; }
  .ch small { color: #FFC83D; }

  /* Knights: royal blue, speed stripes, the court's lines, the emblem */
  .knights { background: repeating-linear-gradient(115deg, rgba(255, 255, 255, 0.05) 0 10px, transparent 10px 26px), linear-gradient(150deg, #3A7BEA, #1C4C94 55%, #0D2A63); }
  .knights .art { left: 50%; top: 10px; height: 112px; transform: translateX(-50%); }
  .knights.wide .art { top: 6px; height: 74px; } /* the emblem says KNIGHTS, the strip below too: no third wordmark */
  .ball { right: -14px; bottom: -20px; width: 88px; opacity: 0.9; }
  .wide .ball { right: 26px; bottom: -10px; width: 62px; }

</style>
