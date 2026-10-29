<script lang="ts">
  // A club's own art on its lanyard (drafts in KBTUapp-OLD/design/lanyards). `wide`: the profile's
  // card keeps its size, so the art is the card's background: the symbol big on the
  // right, the pom-poms or the ball beside the QR; else a band on top of the full-screen badge, the art in the middle.
  // Art: the panther and the Knights emblem cut from the clubs' logos; Knights' ball is three sports in one (they play
  // basketball, football and volleyball: a student's idea from their tryout poster, Oct 20), white line art like the emblem.
  // Moments (photo club, Oct 29): their wordmark on their poster's warm watercolour, film sprockets on the band; on the
  // profile's card only the lens's aperture (lucide's), as the wordmark ran under the name.
  // Faces (a party club): their gradient wordmark over the hands' triangle from their logo, drawn white, on a club
  // night's black with laser beams and lights in the haze.
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
  import guilloche from '../assets/lanyards/kbtu-guilloche.svg?url';
  import KbtuMark from './KbtuMark.svelte';

  let { look, wide = false }: { look: Look; wide?: boolean } = $props();
  // Moments' date stamp, as an old film camera burns it into the corner: today
  const d = new Date(), two = (n: number) => String(n).padStart(2, '0');
  const stamp = `'${two(d.getFullYear() % 100)} ${two(d.getMonth() + 1)} ${two(d.getDate())}`;
</script>

<div class="band {look}" class:wide aria-hidden="true">
  {#if look === 'cheer'}
    <img class="dec" src={wide ? cheerWide : cheerTall} alt="" /><img class="art" src={panther} alt="" />
  {:else if look === 'knights'}
    <svg class="dec" viewBox="0 0 340 112" preserveAspectRatio="xMidYMid slice"><g fill="none" stroke="#fff" stroke-opacity=".16" stroke-width="2">
      <path d="M-10 8H350" /><circle cx="170" cy="8" r="34" /><path d="M120 112V64H220V112" /><path d="M150 64A20 20 0 0 1 190 64" /><path d="M40 112A130 130 0 0 1 300 112" /></g></svg>
    <img class="ball" src={ball} alt="" /><img class="art" src={knights} alt="" />
  {:else if look === 'moments'}
    <i class="leak"></i><span class="date">{stamp}</span>
    {#if wide}<i class="vf"></i><span class="exif"><b>●</b> f/1.8 · 1/250 · ISO 400</span><img class="art" src={aperture} alt="" />
    {:else}<i class="film t"></i><i class="film b"></i><span class="edge">MOMENTS 400 <b>▸</b> 24 <b>▸</b> 24A</span><img class="art" src={moments} alt="" />{/if}
  {:else if look === 'kbtu'}
    <img class="dec gl" src={guilloche} alt="" /><span class="mark"><KbtuMark size={wide ? 150 : 70} /></span>
    {#if !wide}<b class="word">KAZAKH-BRITISH TECHNICAL UNIVERSITY</b>{/if}
  {:else if look === 'faces'}
    <i class="beams"></i><i class="bokeh"></i><img class="hands" src={hands} alt="" />{#if !wide}<img class="art" src={faces} alt="" />{/if}
  {/if}
</div>

<style>
  .band { position: relative; overflow: hidden; height: 124px; color: #fff; }
  .band.wide { position: absolute; inset: 0; height: auto; }
  img { position: absolute; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  .dec { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; }

  /* KBTU, the app's own: the brand's blue and violet, a guilloche as on an ID card, the colonnade */
  .kbtu { background: radial-gradient(110% 90% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), radial-gradient(60% 80% at 100% 100%, rgba(59, 107, 255, 0.5), transparent 70%),
    linear-gradient(155deg, #2A4FD6, #121A3D 72%); }
  .gl { opacity: 0.13; mix-blend-mode: screen; }
  .mark { position: absolute; left: 50%; top: 18px; transform: translateX(-50%); display: flex; color: #fff; filter: drop-shadow(0 6px 18px rgba(124, 77, 255, 0.8)); }
  .wide .mark { left: auto; top: auto; right: -26px; bottom: 36px; transform: rotate(-8deg); opacity: 0.12; filter: none; }
  .word { position: absolute; left: 0; right: 0; bottom: 14px; text-align: center; font: 800 7.5px/1 var(--font-text); letter-spacing: 0.28em; color: rgba(255, 255, 255, 0.7); }
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
  /* the profile's card as a camera's screen: a warm light leak, film grain, the exposure in the corner */
  .leak { position: absolute; inset: 0; pointer-events: none; mix-blend-mode: screen;
    background: radial-gradient(38% 70% at 104% 18%, rgba(255, 176, 92, 0.55), transparent 70%), radial-gradient(30% 60% at -4% 96%, rgba(255, 120, 70, 0.4), transparent 70%); }
  .leak::after { content: ''; position: absolute; inset: 0; opacity: 0.16; mix-blend-mode: overlay;
    background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)'/%3E%3C/svg%3E"); }
  .exif { position: absolute; left: 30px; top: 11px; font: 650 7.5px/1 var(--font-text); letter-spacing: 0.12em; color: rgba(246, 226, 205, 0.75); }
  .exif b { color: #FF5A3C; font-weight: 400; }
  /* a viewfinder's corners around the profile's card */
  .vf { position: absolute; inset: 8px 8px 5px; pointer-events: none; opacity: 0.55; --l: rgba(246, 226, 205, 0.9);
    background: linear-gradient(var(--l), var(--l)) 0 0 / 16px 1.5px, linear-gradient(var(--l), var(--l)) 0 0 / 1.5px 16px,
      linear-gradient(var(--l), var(--l)) 100% 0 / 16px 1.5px, linear-gradient(var(--l), var(--l)) 100% 0 / 1.5px 16px,
      linear-gradient(var(--l), var(--l)) 0 100% / 16px 1.5px, linear-gradient(var(--l), var(--l)) 0 100% / 1.5px 16px,
      linear-gradient(var(--l), var(--l)) 100% 100% / 16px 1.5px, linear-gradient(var(--l), var(--l)) 100% 100% / 1.5px 16px;
    background-repeat: no-repeat; }
  .date { position: absolute; right: 16px; bottom: 22px; font: 700 10px/1 ui-monospace, 'SF Mono', Menlo, monospace; letter-spacing: 0.08em;
    color: #FF9A3C; text-shadow: 0 0 6px rgba(255, 120, 40, 0.9); opacity: 0.9; }
  .wide .date { right: 22px; bottom: 50px; font-size: 9px; } /* just above the strip */
  .moments .art { left: 50%; top: 55%; width: 210px; transform: translate(-50%, -50%); filter: drop-shadow(0 0 14px rgba(255, 228, 200, 0.55)); }
  .band.moments.wide .art { left: auto; top: auto; right: -34px; bottom: -40px; width: 180px; height: auto; transform: none; opacity: 0.2; filter: none; }

  /* Faces: black, a violet-pink-orange glow from their wordmark, the hands' triangle */
  .faces { background: radial-gradient(60% 80% at 50% 110%, rgba(200, 64, 255, 0.5), transparent 70%),
    radial-gradient(40% 70% at 8% 10%, rgba(110, 123, 255, 0.4), transparent 70%),
    radial-gradient(40% 70% at 94% 12%, rgba(255, 150, 60, 0.35), transparent 70%), #07060B; }
  .faces.wide { background: radial-gradient(70% 55% at 100% 100%, rgba(200, 64, 255, 0.42), transparent 70%),
    radial-gradient(60% 50% at 0% 0%, rgba(110, 123, 255, 0.32), transparent 70%), radial-gradient(40% 40% at 100% 0%, rgba(255, 150, 60, 0.22), transparent 70%), #07060B; }
  /* a club night: laser beams fanning from the stage, out-of-focus lights in the haze */
  .beams { position: absolute; inset: 0; pointer-events: none; mix-blend-mode: screen;
    background: repeating-conic-gradient(from 150deg at 50% -18%, transparent 0 5deg, rgba(192, 75, 255, 0.4) 5deg 5.5deg, transparent 5.5deg 11deg),
      repeating-conic-gradient(from 165deg at 18% -30%, transparent 0 7deg, rgba(255, 79, 154, 0.3) 7deg 7.4deg, transparent 7.4deg 14deg),
      repeating-conic-gradient(from 135deg at 84% -30%, transparent 0 8deg, rgba(255, 164, 61, 0.28) 8deg 8.4deg, transparent 8.4deg 15deg);
    -webkit-mask: linear-gradient(#000 10%, transparent 92%); mask: linear-gradient(#000 10%, transparent 92%); }
  .wide .beams { background: repeating-conic-gradient(from 10deg at -8% 110%, transparent 0 4deg, rgba(192, 75, 255, 0.32) 4deg 4.4deg, transparent 4.4deg 9deg),
      repeating-conic-gradient(from 280deg at 108% 112%, transparent 0 6deg, rgba(255, 79, 154, 0.26) 6deg 6.4deg, transparent 6.4deg 12deg);
    -webkit-mask: radial-gradient(120% 120% at 50% 100%, #000 30%, transparent 85%); mask: radial-gradient(120% 120% at 50% 100%, #000 30%, transparent 85%); }
  .bokeh { position: absolute; inset: 0; pointer-events: none; mix-blend-mode: screen;
    background: radial-gradient(circle at 12% 78%, rgba(255, 79, 154, 0.45) 0 5px, transparent 9px), radial-gradient(circle at 28% 30%, rgba(110, 123, 255, 0.4) 0 3px, transparent 6px),
      radial-gradient(circle at 74% 82%, rgba(255, 164, 61, 0.45) 0 6px, transparent 10px), radial-gradient(circle at 90% 40%, rgba(192, 75, 255, 0.45) 0 4px, transparent 8px),
      radial-gradient(circle at 56% 18%, rgba(255, 255, 255, 0.35) 0 2px, transparent 4px), radial-gradient(circle at 40% 88%, rgba(192, 75, 255, 0.35) 0 3px, transparent 7px); }
  .hands { left: 50%; bottom: -6px; width: 300px; transform: translateX(-50%); opacity: 0.16; }
  .faces .art { left: 50%; top: 50%; height: 92px; transform: translate(-50%, -50%); filter: drop-shadow(0 4px 18px rgba(200, 64, 255, 0.45)); }
  .wide .hands { left: auto; right: -40px; bottom: 44px; width: 230px; transform: none; opacity: 0.2; }
</style>
