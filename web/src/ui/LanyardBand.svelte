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
  const gid = 'sxr' + Math.random().toString(36).slice(2, 8); // gradient ids are page-global: the picker draws several
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
  {:else if look === 'studex' && wide}
    <!-- the profile's card: the Oct 29 art (owner, Oct 31: both redraws of it were worse) with what he asked on top: their
         name big in outline, motion (the streaks drift, the arrow glows and a glint runs up it), gloss and depth -->
    <i class="streaks"></i><i class="drift"></i><b class="big">STUDEX</b><b class="big foil" aria-hidden="true">STUDEX</b>
    <svg class="dec sxa par" viewBox="0 0 340 221" preserveAspectRatio="none">
      <defs><linearGradient id={gid} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#EE4A33" /><stop offset="1" stop-color="rgb(169, 33, 26)" /></linearGradient></defs>
      <path d="M0 0H120.9L34 221H0Z" fill="url(#{gid})" /><path class="glow29" d="M114.6 14L33.2 223" vector-effect="non-scaling-stroke" />
      <path class="cut29" d="M99.6 24L114.6 14L118.9 31.5M114.6 14L33.2 223" stroke-width="4" />
      <path class="glint" d="M33.2 223L114.6 14" pathLength="100" vector-effect="non-scaling-stroke" /></svg>
    <i class="flare"></i><i class="gloss"></i>
  {:else if look === 'studex'}
    <!-- their key visual: red and navy split by the white arrow of growth, light streaks along it as on their poster; a
         glint runs up the arrow now and then. On the profile's card the split runs between the photo and the name. -->
    <svg class="dec" viewBox="0 0 340 124" preserveAspectRatio="xMinYMid slice">
      <defs>
        <linearGradient id="{gid}r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F0503A" /><stop offset=".55" stop-color="#C92E22" /><stop offset="1" stop-color="#8E1A14" /></linearGradient>
        <linearGradient id="{gid}s" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0" /><stop offset=".5" stop-color="#fff" /><stop offset="1" stop-color="#fff" stop-opacity="0" /></linearGradient>
      </defs>
        <path d="M0 0H208.2L122.1 124H0Z" fill="url(#{gid}r)" />
        <g class="sxs" stroke="url(#{gid}s)">
          <path d="M10 124L70 38" stroke-opacity=".2" /><path d="M60 110L104 46" stroke-opacity=".14" />
          <path d="M226 124L300 18" stroke-opacity=".2" /><path d="M276 120L340 28" stroke-opacity=".14" /><path d="M320 124L380 38" stroke-opacity=".18" />
        </g>
        <path class="glow" d="M191.6 24L120.7 126" />
        <path class="cut" d="M171 31.6L191.6 24L191.7 46M191.6 24L120.7 126" />
        <path class="glint" d="M120.7 126L191.6 24" pathLength="100" />
    </svg>
    <i class="sheen"></i>
    <b class="sxw"><svg class="cap" viewBox="0 0 40 26"><path d="M20 2L39 10L20 18L1 10Z" fill="#fff" /><path d="M9 14V21C14 25 26 25 31 21V14L20 19Z" fill="#fff" fill-opacity=".85" /><path d="M36 11V20" stroke="#fff" stroke-width="1.5" /></svg>STUD<i>EX</i></b>
      <span class="tag">BE STUDENT. BE EXCELLENT.</span>
  {:else if look === 'kbtu'}
    <img class="dec gl" src={guilloche} alt="" /><span class="mark"><KbtuMark size={wide ? 150 : 70} /></span>
    {#if !wide}<b class="word">KAZAKH-BRITISH TECHNICAL UNIVERSITY</b>{/if}
  {:else if look === 'faces'}
    <i class="beams"></i><i class="bokeh"></i><img class="hands" src={hands} alt="" />{#if !wide}<img class="art" src={faces} alt="" />{/if}
  {/if}
</div>

<style>
  .band { position: relative; overflow: hidden; height: 124px; color: #fff; isolation: isolate; } /* its layers stay inside */
  .band.wide { position: absolute; inset: 0; height: auto; }
  img { position: absolute; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  .dec { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; }

  /* StudEx's profile card, the Oct 29 art: the red wedge, its white cut, speed streaks, halftone, the name faint behind */
  .studex.wide { background: linear-gradient(135deg, rgb(15, 35, 80), rgb(29, 59, 122) 55%, rgb(11, 28, 68)); }
  .streaks { position: absolute; inset: 0; pointer-events: none; z-index: 1;
    background: radial-gradient(60% 80% at 82% 10%, rgba(90, 140, 255, 0.35), transparent 70%), radial-gradient(50% 70% at 10% 100%, rgba(255, 120, 90, 0.3), transparent 70%); }
  /* the speed lines, drifting: one period (46 px) along the gradient's direction (-28deg) and round again, so the loop
     can't be seen; a moved layer, not a repainted background */
  .drift { position: absolute; inset: -60px; pointer-events: none; z-index: 1;
    background: repeating-linear-gradient(-28deg, transparent 0 18px, rgba(255, 255, 255, 0.08) 18px 19px, transparent 19px 46px);
    animation: sxdrift 7s linear infinite; }
  @keyframes sxdrift { to { transform: translate(-21.6px, -40.6px); } }
  /* their name big behind, in outline: seen, but the name on the card stays the one read. Depth with the phone's tilt
     (--gx/--gy from the badge's glass): the name floats nearest and moves most, the arrow less, the streaks least */
  .big { position: absolute; z-index: 1; right: -18px; bottom: 30px; font: italic 900 98px/1 var(--font-display); letter-spacing: -0.04em; white-space: nowrap;
    color: rgba(255, 255, 255, 0.1); /* filled, not outlined: a stroke drew the glyphs' overlaps (squares inside the X) */
    transform: translate(calc(var(--gx, 0) * -4px), calc(var(--gy, 0) * -2.5px)); transition: transform 400ms ease-out; }
  /* a holographic foil inside the letters, its rainbow sliding with the tilt like a real foil print */
  .big.foil { color: transparent; opacity: 0.12; mix-blend-mode: screen;
    background: linear-gradient(100deg, rgb(255, 166, 218), rgb(185, 163, 255), rgb(134, 227, 255), rgb(166, 255, 214), rgb(255, 230, 154), rgb(255, 166, 218)) 0 0 / 300% 100%;
    background-position: calc(50% + var(--gx, 0) * 25%) 0; -webkit-background-clip: text; background-clip: text; }
  .par { transform: translate(calc(var(--gx, 0) * -1.5px), calc(var(--gy, 0) * -1px)) scale(1.02); transition: transform 400ms ease-out; }
  .streaks { transform: translate(calc(var(--gx, 0) * 1.5px), calc(var(--gy, 0) * 1px)) scale(1.02); }
  /* a star of light at the arrow's tip when the glint reaches it (the glint's cycle: 5 s, from 1 s, arrives at 30 %) */
  .flare { position: absolute; z-index: 1; left: calc(33.7% - 22px); top: calc(6.3% - 22px); width: 44px; height: 44px; pointer-events: none; opacity: 0; mix-blend-mode: screen;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.95) 0 2px, rgba(255, 255, 255, 0.5) 4px, transparent 60%),
      linear-gradient(90deg, transparent 20%, rgba(255, 255, 255, 0.7) 50%, transparent 80%) center / 100% 1.5px no-repeat,
      linear-gradient(transparent 20%, rgba(255, 255, 255, 0.7) 50%, transparent 80%) center / 1.5px 100% no-repeat;
    animation: sxflare 5s 1s ease-out infinite; }
  @keyframes sxflare { 0%, 24% { opacity: 0; transform: scale(0.3) rotate(0deg); } 31% { opacity: 1; transform: scale(1.1) rotate(20deg); } 48%, 100% { opacity: 0; transform: scale(0.6) rotate(45deg); } }
  /* the arrow lit: a soft glow breathing under the white cut */
  .glow29 { fill: none; stroke: rgba(255, 255, 255, 0.5); stroke-width: 10; stroke-linecap: round; filter: blur(5px); animation: sxbreathe 3.2s ease-in-out infinite; }
  @keyframes sxbreathe { 50% { opacity: 0.35; } }
  /* gloss and depth, like a printed plastic card: a curved light from the top, a bevel along the edge */
  .gloss { position: absolute; inset: 0; z-index: 1; pointer-events: none; border-radius: inherit;
    background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0.05) 55%, transparent 70%),
      linear-gradient(180deg, transparent 60%, rgba(0, 0, 0, 0.18));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), inset 0 -2px 8px rgba(0, 0, 0, 0.3); }
  @media (prefers-reduced-motion: reduce) { .drift, .glow29 { animation: none; } .flare { display: none; } }
  :global(html.lowfx) .drift, :global(html.lowfx) .glow29 { animation: none; }
  :global(html.lowfx) .flare, :global(html.lowfx) .foil { display: none; }
  .cut29 { fill: none; stroke: rgba(255, 255, 255, 0.92); stroke-linecap: round; stroke-linejoin: round; }
  .sxa { z-index: 0; }
  /* StudEx (redrawn Oct 31 from their brand kit: the Oct 29 wedge with halftone and a ghost name read as clutter): deep
     navy lit from the top right, the red half in their poster's gradient, white streaks along the arrow's slope, the
     arrow itself with a soft glow, a glint running up it every few seconds */
  .studex { background: radial-gradient(70% 90% at 92% 0%, rgba(74, 118, 230, 0.55), transparent 70%), linear-gradient(160deg, rgb(26, 56, 120), rgb(16, 38, 87) 55%, rgb(10, 24, 56)); }
  .sxs { fill: none; stroke-width: 1.5; stroke-linecap: round; }
  .cut { fill: none; stroke: rgba(255, 255, 255, 1); stroke-width: 3.5; stroke-linecap: round; stroke-linejoin: round; }
  .cut { stroke-width: 4.5; }
  .glow { fill: none; stroke: rgba(255, 255, 255, 0.35); stroke-width: 12; stroke-linecap: round; filter: blur(6px); }
  .glint { fill: none; stroke: rgba(255, 255, 255, 1); stroke-width: 6; stroke-linecap: round; stroke-dasharray: 14 120; stroke-dashoffset: 14; opacity: 0.9;
    filter: drop-shadow(0 0 6px rgba(255, 255, 255, 1)); animation: sxglint 5s 1s cubic-bezier(.5, 0, .3, 1) infinite; }
  @keyframes sxglint { 0% { stroke-dashoffset: 14; } 30%, 100% { stroke-dashoffset: -106; } }
  @media (prefers-reduced-motion: reduce) { .glint { display: none; } }
  :global(html.lowfx) .glint, :global(html.lowfx) .glow { display: none; }
  /* a glossy top light over both halves, like printed card stock */
  .sheen { position: absolute; inset: 0; pointer-events: none; background: linear-gradient(170deg, rgba(255, 255, 255, 0.14), transparent 38%); }
  .sxw { position: absolute; left: 22px; top: 36px; font: 900 40px/1 var(--font-display); letter-spacing: -0.02em; color: #fff;
    text-shadow: 0 6px 20px rgba(0, 0, 0, 0.3); }
  .sxw i { font-style: normal; }
  .cap { position: absolute; left: -10px; top: -15px; width: 30px; transform: rotate(-16deg); filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3)); }
  .tag { position: absolute; right: 16px; bottom: 14px; font: 800 7.5px/1 var(--font-text); letter-spacing: 0.24em; color: rgba(255, 255, 255, 0.7); }
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
