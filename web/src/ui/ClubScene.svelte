<script lang="ts">
  // The other clubs' lanyards (Nov 2, round 2): each its own scene, drawn as layers (assets/lanyards/scenes, made by
  // .claude/reports/club-lanyards/gen-scenes.py; the figures cut from the clubs' logos by make-marks.sh). The template
  // (lib/awards.ts CLUB_LOOKS: strap, strip, QR, colours) is the frame; this is the art. The grammar of the five drawn by
  // hand (ui/LanyardBand, .claude/reports/lanyard-standard-spec.md): far layers move with the tilt (base.css .z), the
  // figure stands on the strip on the QR's axis over its contact shadow; one quiet loop at most, transform and opacity
  // only, paused with the card (Hero's .rest), still under reduced motion and power saving, static in the picker.
  // `wide`: the profile's card (the art to the right, the QR's well at x 297); else the badge's band (MyQr), centred.
  import type { Look } from '../lib/awards';
  import crown from '../assets/lanyards/mk-crown.webp';
  import crystal from '../assets/lanyards/crystal.webp';
  import derrick from '../assets/lanyards/spe-derrick-dark.webp';
  import arthouse from '../assets/lanyards/arthouse.webp';
  import people from '../assets/lanyards/qairym-people-dark.webp';
  import shadeWord from '../assets/lanyards/shade-word-red.webp';
  import jccBack from '../assets/lanyards/jcc-back.webp';
  import jccSakura from '../assets/lanyards/jcc-sakura.webp';
  import jccLogo from '../assets/lanyards/jcc-logo.webp';
  import mic from '../assets/lanyards/scenes/ah-mic.svg?url';
  import keys from '../assets/lanyards/scenes/ah-keys.svg?url';

  let { look, wide = false, qr = false }: { look: Look; wide?: boolean; qr?: boolean } = $props();
  const SC = import.meta.glob('../assets/lanyards/scenes/*.svg', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
  // a layer in this framing: mk-near -> mk-near-card.svg / mk-near-band.svg
  const L = (n: string) => SC[`../assets/lanyards/scenes/${n}-${wide ? 'card' : 'band'}.svg`];
</script>

<div class="sc {look}" class:wide class:qr aria-hidden="true">
  {#if look === 'mountainkingskbtu'}
    <!-- a range at dawn: an aurora and stars behind, the crown in the sky, three ridges, snow falling -->
    <img class="l z sky" src={L('mk-sky')} alt="" />
    <span class="crw z"><img src={crown} alt="" /></span>
    <img class="l z far" src={L('mk-far')} alt="" /><img class="l" src={L('mk-mid')} alt="" /><img class="l z near" src={L('mk-near')} alt="" />
    <i class="snow"></i>
  {:else if look === 'crystalkbtu'}
    <!-- an ice field of facets, a prism's glint passing now and then; on the badge's band their diamond under its crown (on
         the card it is the medallion: Hero's OrgMedal) -->
    <img class="l z far" src={L('cr-facets')} alt="" /><i class="halo"></i><span class="prw"><i class="prism"></i></span>
    {#if !wide}<span class="hero"><img src={crystal} alt="" /></span>{/if}
  {:else if look === 'spekbtu'}
    <!-- an oil field at dusk: their map's dots in the sky, the sun on the horizon, the derrick against it -->
    <img class="l z far" src={L('spe-map')} alt="" /><i class="sun"></i>
    <img class="l" src={L('spe-ground')} alt="" /><span class="fig rig"><img src={derrick} alt="" /></span>
  {:else if look === 'aichekbtu'}
    <!-- a lab at night: a molecule turning in the dark far behind, glass catching the light; their flask big on the right,
         its liquid glowing, bubbles rising in it, the light through it thrown on the card as caustics -->
    <i class="tide"></i><img class="l z far" src={L('ai-mol')} alt="" /><i class="pane"></i>
    <span class="flw z"><img class="l" src={L('ai-flask')} alt="" /><span class="bub"><i></i><i></i><i></i></span></span>
  {:else if look === 'bigcitylightskbtu'}
    <!-- the city at night: neon in the haze, a skyline, its windows, some lighting up; the lights out of focus in front -->
    <i class="neon"></i><img class="l" src={L('bcl-city')} alt="" /><img class="l win" src={L('bcl-win')} alt="" />
    <img class="l z near" src={L('bcl-bokeh')} alt="" />
  {:else if look === 'arthousekbtu'}
    <!-- a stage: velvet, the valance, one warm spotlight on the microphone, a sound wave, the piano's keys at the foot -->
    <i class="velvet"></i><span class="spw"><i class="spot"></i></span><i class="pool"></i>
    <img class="l z far wave" src={L('ah-wave')} alt="" /><img class="l" src={L('ah-valance')} alt="" />
    {#if wide}<span class="fig z"><img src={mic} alt="" /></span>{:else}<img class="word" src={arthouse} alt="" />{/if}
    <img class="keys" src={keys} alt="" />
  {:else if look === 'qairymdylyqkbtu'}
    <!-- a sunrise: the sun behind the hill, the three of them on it, warm light rising -->
    <img class="l z far" src={L('qa-sun')} alt="" /><i class="motes"></i>
    <img class="l" src={L('qa-hill')} alt="" /><span class="fig ppl"><img src={people} alt="" /></span>
  {:else if look === 'shadekbtu'}
    <!-- paper. The card (round 5, owner: their official logo, not our smear): their brush-lettered SHADE painted across
         the whole sheet, their line from the logo set small at the top; the brush itself is the medallion (OrgMedal).
         The badge's band: their red swept across it, the word in the middle -->
    <i class="paper"></i>
    {#if wide}<img class="sw z" src={shadeWord} alt="" /><span class="shtag">CREATIVE PEOPLE CLUB</span>
    {:else}<img class="l z near" src={L('sh-strokes')} alt="" /><img class="word" src={shadeWord} alt="" />{/if}
  {:else if look === 'japanesecultureclub'}
    <!-- their own layers (Nov 2): the pink sky with its pale sun and their shanyrak far, the sakura near, petals drifting
         between; on the badge's band their whole logo in the middle -->
    <img class="l z far jb" src={jccBack} alt="" /><i class="petals"></i><img class="l z near js" src={jccSakura} alt="" />
    {#if !wide}<span class="hero jl"><img src={jccLogo} alt="" /></span>{/if}
  {/if}
  <i class="gloss"></i>
</div>

<style>
  .sc { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
  img { position: absolute; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  i { position: absolute; display: block; pointer-events: none; }
  /* a drawn layer covers the card, anchored at its foot: on the card to the right (the art is there; 320 px loses the
     left), on the band in the middle */
  .l { inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: 100% 100%; }
  .sc:not(.wide) .l { object-position: 50% 100%; }
  .far { --z: -2; --zs: 1.03; }
  .near { --z: 3; --zs: 1.03; }
  .sky { --z: -3; --zs: 1.04; }

  /* the figure: on the card it stands on the strip on the QR's axis (43 px from the right), 44 px tall (64 on someone
     else's card, where it has the column alone), over a still contact shadow; on the band, centred */
  .fig { position: absolute; right: 7px; bottom: 40px; width: 72px; height: 44px; display: flex; justify-content: center; align-items: flex-end; --z: 5; }
  .fig img { position: static; height: 100%; max-width: 100%; object-fit: contain; }
  .wide:not(.qr) .fig { height: 64px; }
  .sc:not(.wide) .fig { right: auto; left: 50%; bottom: 10px; width: 120px; height: 92px; margin-left: -60px; }
  /* the club's wordmark on the badge's band */
  .word { left: 50%; top: 22px; height: 80px; max-width: 74%; object-fit: contain; transform: translateX(-50%); }

  .gloss { inset: 0; border-radius: inherit; background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.14), transparent 65%), linear-gradient(180deg, transparent 65%, rgba(0, 0, 0, 0.14));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), inset 0 -2px 8px rgba(0, 0, 0, 0.22); }

  /* ---- Mountain Kings: night going to dawn behind the range ---- */
  .mountainkingskbtu { background: radial-gradient(70% 55% at 82% 78%, rgba(255, 184, 176, 0.42), transparent 70%), radial-gradient(60% 50% at 100% 100%, rgba(255, 214, 160, 0.3), transparent 70%),
    linear-gradient(172deg, rgb(6, 10, 40), rgb(16, 32, 104) 55%, rgb(52, 84, 186)); }
  .mountainkingskbtu:not(.wide) { background: radial-gradient(60% 70% at 50% 92%, rgba(255, 184, 176, 0.45), transparent 70%), linear-gradient(180deg, rgb(6, 10, 40), rgb(18, 36, 112) 60%, rgb(46, 76, 176)); }
  .crw { position: absolute; right: 6px; top: -8px; width: 190px; --z: -2; }
  .crw img { position: static; display: block; width: 100%; opacity: 0.1; }
  .sc:not(.wide) .crw { right: auto; left: 50%; top: 12px; width: 120px; margin-left: -60px; }
  .sc:not(.wide) .crw img { opacity: 0.95; }
  /* snow: a tile of flakes drifting down and a little left, one tile per period, so the loop can't be seen */
  .snow { left: 0; top: -100px; width: calc(100% + 100px); height: calc(100% + 100px); background: url('../assets/lanyards/scenes/mk-snow.svg') 0 0 / 100px 100px;
    opacity: 0.7; animation: mksnow 22s linear infinite; }
  @keyframes mksnow { to { transform: translate(-100px, 100px); } }

  /* ---- Crystal: cold teal, the light from the top right ---- */
  .crystalkbtu { background: radial-gradient(70% 90% at 100% 0%, rgba(140, 240, 255, 0.35), transparent 65%), linear-gradient(160deg, rgb(10, 52, 62), rgb(14, 70, 84) 50%, rgb(5, 30, 38)); }
  .crystalkbtu:not(.wide) { background: radial-gradient(60% 80% at 50% 30%, rgba(140, 240, 255, 0.35), transparent 70%), linear-gradient(180deg, rgb(12, 62, 76), rgb(14, 70, 84)); }
  .halo { right: -37px; bottom: -4px; width: 160px; height: 132px; background: radial-gradient(closest-side, rgba(150, 245, 255, 0.5), transparent); }
  .sc:not(.wide) .halo { right: auto; left: 50%; bottom: -10px; margin-left: -80px; }
  /* a prism's glint: a soft band of split light crossing the card once every 9 s */
  .prw { position: absolute; inset: 0; overflow: hidden; -webkit-mask: linear-gradient(90deg, transparent 25%, black 60%); mask: linear-gradient(90deg, transparent 25%, black 60%); }
  .prism { left: -90px; top: -40px; width: 70px; height: calc(100% + 80px); transform: translateX(0) rotate(18deg); opacity: 0;
    background: linear-gradient(90deg, transparent, rgba(255, 150, 210, 0.22) 25%, rgba(255, 255, 255, 0.5) 45%, rgba(140, 240, 255, 0.3) 60%, rgba(255, 236, 150, 0.2) 75%, transparent);
    animation: crprism 9s 1.4s cubic-bezier(.45, 0, .3, 1) infinite; }
  @keyframes crprism { 0% { transform: translateX(0) rotate(18deg); opacity: 0; } 4% { opacity: 1; } 18% { opacity: 1; } 22%, 100% { transform: translateX(560px) rotate(18deg); opacity: 0; } }
  .crystalkbtu.wide .far { -webkit-mask: linear-gradient(90deg, transparent 22%, black 62%); mask: linear-gradient(90deg, transparent 22%, black 62%); } /* the ice away from the text */
  /* the diamond, big, cut by the right edge, the crown under the QR's corner; near with the tilt */
  .hero { position: absolute; }
  .hero img { position: static; display: block; height: 100%; filter: drop-shadow(0 0 14px rgba(150, 245, 255, 0.45)); }
  .sc:not(.wide) .hero { left: 0; right: 0; bottom: 6px; height: 104px; display: flex; justify-content: center; }

  /* ---- SPE: dusk ---- */
  /* the sky to the horizon (68 % down the card, above the strip): navy, steel, a mauve band, the sunset's orange */
  .spekbtu { background: radial-gradient(45% 40% at 87% 68%, rgba(255, 170, 110, 0.6), transparent 70%),
    linear-gradient(180deg, rgb(8, 22, 52), rgb(20, 50, 96) 36%, rgb(70, 82, 130) 52%, rgb(190, 116, 112) 62%, rgb(246, 160, 100) 68%, rgb(10, 30, 64) 68.5%); }
  .spekbtu .far { opacity: 0.32; -webkit-mask: linear-gradient(100deg, transparent 20%, black 60%); mask: linear-gradient(100deg, transparent 20%, black 60%); }
  /* the sun on the horizon behind the derrick, its glow breathing slowly */
  .sun { right: -7px; bottom: 52px; width: 100px; height: 100px; margin-bottom: -50px; border-radius: 50%; clip-path: inset(0 0 50% 0);
    background: radial-gradient(closest-side, rgb(255, 236, 196) 0 18%, rgba(255, 190, 120, 0.85) 26%, rgba(255, 150, 90, 0.35) 55%, transparent);
    animation: spsun 14s ease-in-out infinite alternate; }
  .sc:not(.wide) .sun { right: auto; left: 50%; bottom: 22px; margin-left: -50px; }
  .spekbtu:not(.wide) { background: radial-gradient(50% 50% at 50% 82%, rgba(255, 170, 110, 0.6), transparent 70%), linear-gradient(180deg, rgb(8, 22, 52), rgb(26, 60, 110) 45%, rgb(170, 110, 120) 72%, rgb(246, 160, 100) 82%, rgb(10, 30, 64) 82.5%); }
  @keyframes spsun { from { opacity: 0.8; } to { opacity: 1; } }
  .rig { right: -4px; bottom: 52px; height: 104px; } /* on the horizon, tall: its crown rises behind the medallion */
  .wide:not(.qr) .rig { height: 70px; }
  .sc:not(.wide) .rig { bottom: 22px; height: 94px; }

  /* ---- AIChE: their blue going to a lab's night, the glass and its glow ---- */
  .aichekbtu { background: radial-gradient(60% 80% at 92% 70%, rgba(40, 170, 255, 0.45), transparent 70%), linear-gradient(160deg, rgb(16, 84, 152), rgb(8, 52, 104) 50%, rgb(3, 20, 48)); }
  .aichekbtu:not(.wide) { background: radial-gradient(50% 80% at 50% 70%, rgba(40, 170, 255, 0.45), transparent 70%), linear-gradient(180deg, rgb(14, 74, 140), rgb(6, 40, 86)); }
  .tide { inset: 0; background: radial-gradient(40% 30% at 20% 10%, rgba(140, 200, 255, 0.16), transparent 70%); }
  /* light on a sheet of glass: a soft band and two thin edges */
  .pane { inset: 0; background: linear-gradient(115deg, transparent 52%, rgba(255, 255, 255, 0.05) 53%, rgba(255, 255, 255, 0.09) 62%, rgba(255, 255, 255, 0.18) 62.4%, transparent 63%, transparent 66%, rgba(255, 255, 255, 0.1) 66.3%, transparent 66.8%); }
  .flw { position: absolute; inset: 0; --z: 2; }
  /* bubbles rising in the liquid, from the bulb's floor to the surface, fading */
  .bub { position: absolute; right: 16px; bottom: 44px; width: 20px; height: 6px; }
  .sc:not(.wide) .bub { right: auto; left: 50%; bottom: 16px; margin-left: -10px; }
  .bub i { left: 6px; bottom: 0; width: 4px; height: 4px; border-radius: 50%; background: radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.95), rgba(200, 250, 255, 0.35) 60%, transparent 70%);
    opacity: 0; animation: aibub 6s ease-in infinite; }
  .bub i:nth-child(2) { left: 14px; width: 3px; height: 3px; animation-delay: 2s; }
  .bub i:nth-child(3) { left: 0; width: 2.5px; height: 2.5px; animation-delay: 4s; }
  @keyframes aibub { 0% { opacity: 0; transform: translate(0, 0); } 15% { opacity: 1; } 80% { opacity: 0.9; } 100% { opacity: 0; transform: translate(2px, -28px); } }

  /* ---- Big City Lights: night, neon in the haze ---- */
  .bigcitylightskbtu { background: linear-gradient(180deg, rgb(14, 6, 34), rgb(38, 10, 70) 55%, rgb(92, 20, 110) 80%, rgb(170, 40, 120)); }
  .neon { inset: 0; background: radial-gradient(60% 45% at 78% 100%, rgba(255, 70, 160, 0.55), transparent 70%), radial-gradient(50% 40% at 30% 100%, rgba(150, 70, 255, 0.45), transparent 70%); }
  .sc:not(.wide) .neon { background: radial-gradient(70% 55% at 50% 100%, rgba(255, 70, 160, 0.55), transparent 70%), radial-gradient(50% 40% at 15% 100%, rgba(150, 70, 255, 0.45), transparent 70%); }
  .win { opacity: 0; animation: bcwin 11s ease-in-out infinite alternate; } /* windows lighting up, slowly, then out */
  @keyframes bcwin { 0%, 30% { opacity: 0; } 70%, 100% { opacity: 1; } }

  /* ---- ArtHouse: a stage ---- */
  .arthousekbtu { background: linear-gradient(180deg, rgb(58, 10, 22), rgb(34, 6, 14) 60%, rgb(18, 3, 8)); }
  /* the velvet's folds, deepest at the edges */
  .velvet { inset: 0; opacity: 0.55; background: repeating-linear-gradient(90deg, rgba(0, 0, 0, 0.35) 0 4px, rgba(255, 80, 100, 0.08) 9px, rgba(0, 0, 0, 0.35) 14px);
    -webkit-mask: linear-gradient(90deg, black, transparent 30% 70%, black); mask: linear-gradient(90deg, black, transparent 30% 70%, black); }
  /* one warm spotlight from above, swaying a little as a follow-spot does */
  .spw { position: absolute; right: -57px; top: -20px; width: 200px; height: calc(100% - 20px); transform-origin: 50% 0; animation: ahspot 14s ease-in-out infinite alternate; }
  .spot { inset: 0; background: linear-gradient(180deg, rgba(255, 214, 150, 0.32), rgba(255, 200, 130, 0.12) 85%, transparent); clip-path: polygon(46% 0, 54% 0, 80% 100%, 20% 100%); }
  @keyframes ahspot { from { transform: rotate(-2.5deg); } to { transform: rotate(2.5deg); } }
  .pool { right: 3px; bottom: 34px; width: 80px; height: 18px; background: radial-gradient(closest-side, rgba(255, 210, 150, 0.45), transparent); }
  .sc:not(.wide) .spw { right: auto; left: 50%; margin-left: -100px; }
  .sc:not(.wide) .pool { right: auto; left: 50%; bottom: 12px; margin-left: -60px; width: 120px; }
  .arthousekbtu .fig { height: 46px; }
  .wave { opacity: 0.6; }
  .keys { left: 0; right: 0; bottom: 0; width: 100%; height: 14px; object-fit: cover; object-position: 0 0; opacity: 0.9; } /* the card's foot, under the strip */
  .sc:not(.wide) .keys { height: 10px; }
  .arthousekbtu .word { top: 26px; height: 62px; }

  /* ---- Qairymdylyq: sunrise ---- */
  .qairymdylyqkbtu { background: linear-gradient(176deg, rgb(70, 16, 56), rgb(150, 34, 92) 42%, rgb(232, 96, 82) 72%, rgb(255, 176, 96)); }
  .motes { left: 0; top: 0; width: 100%; height: calc(100% + 100px); background: url('../assets/lanyards/scenes/qa-motes.svg') 0 0 / 100px 100px;
    -webkit-mask: linear-gradient(90deg, transparent 30%, black 70%); mask: linear-gradient(90deg, transparent 30%, black 70%); animation: qamotes 26s linear infinite; }
  .sc:not(.wide) .motes { -webkit-mask: radial-gradient(60% 90% at 50% 100%, black, transparent); mask: radial-gradient(60% 90% at 50% 100%, black, transparent); }
  @keyframes qamotes { to { transform: translateY(-100px); } }
  .ppl { bottom: 46px; height: 30px; } /* on the hill, in front of the sun */
  .wide:not(.qr) .ppl { height: 40px; }
  .sc:not(.wide) .ppl { bottom: 12px; height: 46px; }

  /* ---- Shade: cream paper, its grain ---- */
  .shadekbtu { background: radial-gradient(90% 90% at 20% 0%, rgb(252, 248, 240), transparent 70%), linear-gradient(160deg, rgb(246, 238, 226), rgb(236, 224, 206)); }
  .paper { inset: 0; opacity: 0.4; mix-blend-mode: multiply;
    background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.75' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .55 0 0 0 0 .45 0 0 0 0 .35 0 0 0 .5 0'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E"); }
  .shadekbtu .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.35), transparent 65%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7), inset 0 0 0 1px rgba(120, 60, 40, 0.12); }
  .sw { left: 4%; top: 50%; width: 104%; margin-top: -46px; opacity: 0.2; transform: rotate(-5deg); mix-blend-mode: multiply; --z: -2; --zs: 1.03; }
  .shtag { position: absolute; left: 18px; top: 10px; display: flex; gap: 6px; font: 800 6.5px/1 var(--font-text); letter-spacing: 0.2em; color: rgb(200, 0, 0); opacity: 0.85; }
  .shadekbtu .word { top: 30px; height: 56px; }

  /* ---- Japanese Culture: their pink, their shanyrak top right (behind the QR on the card), sakura near ---- */
  .japanesecultureclub { background: rgb(224, 172, 190); }
  .jb { object-position: 100% 0; --z: -3; }
  .sc:not(.wide) .jb { object-position: 100% 30%; }
  .js { object-position: 100% 0; --z: 4; --zs: 1.05; }
  .petals { left: -120px; top: -120px; width: calc(100% + 240px); height: calc(100% + 240px); background: url('../assets/lanyards/scenes/jcc-petals.svg') 0 0 / 120px 120px;
    opacity: 0.85; animation: jcpetal 24s linear infinite; }
  @keyframes jcpetal { to { transform: translate(120px, 120px); } } /* one tile down and to the right: the wind, no seam */
  .japanesecultureclub .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.3), transparent 65%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), inset 0 0 0 1px rgba(90, 30, 60, 0.12); }
  .jl { height: 96px; }
  .jl img { filter: drop-shadow(0 6px 14px rgba(90, 30, 60, 0.35)); }

  /* still: no loop under reduced motion or power saving; each scene's resting frame is a whole picture */
  @media (prefers-reduced-motion: reduce) { .snow, .prism, .sun, .bub i, .win, .spw, .motes, .petals { animation: none; } .win { opacity: 0.6; } }
  :global(html.lowfx) .snow, :global(html.lowfx) .prism, :global(html.lowfx) .sun, :global(html.lowfx) .bub i, :global(html.lowfx) .win,
  :global(html.lowfx) .spw, :global(html.lowfx) .motes, :global(html.lowfx) .petals { animation: none; }
  :global(html.lowfx) .win { opacity: 0.6; }
</style>
