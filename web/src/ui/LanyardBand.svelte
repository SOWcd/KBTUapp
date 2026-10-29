<script lang="ts">
  // A club's own art on its lanyard (drafts in KBTUapp-OLD/design/lanyards). `wide`: the profile's
  // card keeps its size, so the art is the card's background: the symbol big on the
  // right, the pom-poms or the ball beside the QR; else a band on top of the full-screen badge, the art in the middle.
  // Art: the panther and the Knights emblem cut from the clubs' logos; Knights' ball is three sports in one (they play
  // basketball, football and volleyball: a student's idea from their tryout poster, Oct 20), white line art like the emblem.
  // Moments (photo club, Oct 29): their wordmark on their poster's warm watercolour, film sprockets on the band; on the
  // profile's card only the lens's aperture (lucide's), as the wordmark ran under the name.
  // Faces: their gradient wordmark over the hands' triangle from their logo, drawn white, on black.
  import type { Look } from '../lib/awards';
  import panther from '../assets/lanyards/panther.webp';
  import knights from '../assets/lanyards/knights.webp';
  import cheerWide from '../assets/lanyards/cheer-wide.svg?url';
  import cheerTall from '../assets/lanyards/cheer-tall.svg?url';
  import ball from '../assets/lanyards/knights-ball.svg?url';
  import moments from '../assets/lanyards/moments.webp';
  import aperture from '../assets/lanyards/moments-aperture.svg?url';
  import faces from '../assets/lanyards/faces.webp';
  import hands from '../assets/lanyards/faces-hands.webp';

  let { look, wide = false }: { look: Look; wide?: boolean } = $props();
</script>

<div class="band {look}" class:wide aria-hidden="true">
  {#if look === 'cheer'}
    <img class="dec" src={wide ? cheerWide : cheerTall} alt="" /><img class="art" src={panther} alt="" />
  {:else if look === 'knights'}
    <svg class="dec" viewBox="0 0 340 112" preserveAspectRatio="xMidYMid slice"><g fill="none" stroke="#fff" stroke-opacity=".16" stroke-width="2">
      <path d="M-10 8H350" /><circle cx="170" cy="8" r="34" /><path d="M120 112V64H220V112" /><path d="M150 64A20 20 0 0 1 190 64" /><path d="M40 112A130 130 0 0 1 300 112" /></g></svg>
    <img class="ball" src={ball} alt="" /><img class="art" src={knights} alt="" />
  {:else if look === 'moments'}
    {#if wide}<i class="vf"></i><img class="art" src={aperture} alt="" />
    {:else}<i class="film t"></i><i class="film b"></i><span class="edge">MOMENTS 400 <b>▸</b> 24 <b>▸</b> 24A</span><img class="art" src={moments} alt="" />{/if}
  {:else if look === 'faces'}
    <img class="hands" src={hands} alt="" />{#if !wide}<img class="art" src={faces} alt="" />{/if}
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

  /* Moments: terracotta, rust and olive washes as on their poster, a strip of film above and below the wordmark */
  .moments { background: radial-gradient(55% 75% at 28% 62%, rgba(122, 116, 66, 0.95), transparent 72%),
    radial-gradient(45% 70% at 82% 30%, rgba(143, 62, 38, 0.9), transparent 70%),
    radial-gradient(35% 55% at 95% 95%, rgba(236, 205, 178, 0.55), transparent 70%), linear-gradient(160deg, #C46D47, #A24F31); }
  .moments.wide { background: radial-gradient(60% 55% at 92% 88%, rgba(122, 116, 66, 0.9), transparent 72%),
    radial-gradient(70% 60% at 0% 0%, rgba(214, 137, 98, 0.7), transparent 70%), linear-gradient(165deg, #A9563A, #6E3322 70%, #4A2318); }
  .film { position: absolute; left: 0; right: 0; height: 16px; background: #1B1310; }
  .film::after { content: ''; position: absolute; inset: 4px 0; background: repeating-linear-gradient(90deg, transparent 0 5px, #E9D2BA 5px 13px, transparent 13px 18px); }
  .film.t { top: 0; }
  .film.b { bottom: 0; }
  /* the film's edge print, as on a real negative */
  .edge { position: absolute; left: 14px; top: 19px; font: 700 7px/1 var(--font-text); letter-spacing: 0.18em; color: #F2B35C; opacity: 0.85; }
  .edge b { font-weight: 400; }
  /* a viewfinder's corners around the profile's card */
  .vf { position: absolute; inset: 8px 8px 5px; pointer-events: none; opacity: 0.55; --l: rgba(246, 226, 205, 0.9);
    background: linear-gradient(var(--l), var(--l)) 0 0 / 16px 1.5px, linear-gradient(var(--l), var(--l)) 0 0 / 1.5px 16px,
      linear-gradient(var(--l), var(--l)) 100% 0 / 16px 1.5px, linear-gradient(var(--l), var(--l)) 100% 0 / 1.5px 16px,
      linear-gradient(var(--l), var(--l)) 0 100% / 16px 1.5px, linear-gradient(var(--l), var(--l)) 0 100% / 1.5px 16px,
      linear-gradient(var(--l), var(--l)) 100% 100% / 16px 1.5px, linear-gradient(var(--l), var(--l)) 100% 100% / 1.5px 16px;
    background-repeat: no-repeat; }
  .moments .art { left: 50%; top: 55%; width: 210px; transform: translate(-50%, -50%); filter: drop-shadow(0 0 14px rgba(255, 228, 200, 0.55)); }
  .band.moments.wide .art { left: auto; top: auto; right: -34px; bottom: -40px; width: 180px; height: auto; transform: none; opacity: 0.2; filter: none; }

  /* Faces: black, a violet-pink-orange glow from their wordmark, the hands' triangle */
  .faces { background: radial-gradient(60% 80% at 50% 110%, rgba(200, 64, 255, 0.5), transparent 70%),
    radial-gradient(40% 70% at 8% 10%, rgba(110, 123, 255, 0.4), transparent 70%),
    radial-gradient(40% 70% at 94% 12%, rgba(255, 150, 60, 0.35), transparent 70%), #07060B; }
  .faces.wide { background: radial-gradient(70% 55% at 100% 100%, rgba(200, 64, 255, 0.42), transparent 70%),
    radial-gradient(60% 50% at 0% 0%, rgba(110, 123, 255, 0.32), transparent 70%), radial-gradient(40% 40% at 100% 0%, rgba(255, 150, 60, 0.22), transparent 70%), #07060B; }
  .hands { left: 50%; bottom: -6px; width: 300px; transform: translateX(-50%); opacity: 0.16; }
  .faces .art { left: 50%; top: 50%; height: 92px; transform: translate(-50%, -50%); filter: drop-shadow(0 4px 18px rgba(200, 64, 255, 0.45)); }
  .wide .hands { left: auto; right: -40px; bottom: 44px; width: 230px; transform: none; opacity: 0.2; }
</style>
