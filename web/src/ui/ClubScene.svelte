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
  import chEmblem from '../assets/lanyards/choice-emblem.webp'; // their logo cut off its navy (round 5b)
  import jccBack from '../assets/lanyards/jcc-back.webp';
  import keys from '../assets/lanyards/scenes/ah-keys.svg?url';
  import oteWord from '../assets/lanyards/ote-word.webp';
  import animeBack from '../assets/lanyards/anime-back.webp'; // their own art, the mock's frame painted out (new3/cut-new3.py)
  import magWord from '../assets/lanyards/kbtumag-mark.webp';
  // round 10's marks (.claude/reports/club-lanyards/round10/gen/gen.sh), on the badge's band over round 11's scenes
  import enLogo from '../assets/lanyards/enactus-logo.webp';
  import caseLogo from '../assets/lanyards/case-logo.webp';
  import knlLogo from '../assets/lanyards/knl-logo.webp';
  import litLogo from '../assets/lanyards/literature-logo.webp';
  import tumLogo from '../assets/lanyards/tumar-logo.webp';
  import w3St from '../assets/lanyards/web3-st.webp';
  import zhHeart from '../assets/lanyards/zhurek-heart.webp';

  let { look, wide = false, qr = false }: { look: Look; wide?: boolean; qr?: boolean } = $props();
  const SC = import.meta.glob('../assets/lanyards/scenes/*-band.svg', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
  // the card's layers as pictures (tools/scene-rasters.mjs: decoded once off the main thread, not the SVG re-rasterised at 3x)
  const CARD = import.meta.glob('../assets/lanyards/scenes/*-card.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
  // a layer in this framing: mk-near -> mk-near-card.webp / mk-near-band.svg
  // round 11's scenes (their files' prefix) and the marks on their badge's band
  const SCN: Partial<Record<Look, string>> = { enactuskbtu: 'en', caseclubkbtu: 'cs', knlknolimits: 'knl', literatureclub: 'lit', tumarorchestrakbtu: 'tm', web: 'w3', zhylyzhurekkbtu: 'zh' };
  const MARK: Partial<Record<Look, string>> = { enactuskbtu: enLogo, caseclubkbtu: caseLogo, knlknolimits: knlLogo, literatureclub: litLogo, tumarorchestrakbtu: tumLogo, web: w3St, zhylyzhurekkbtu: zhHeart };
  const L = (n: string) => wide ? CARD[`../assets/lanyards/scenes/${n}-card.webp`] : SC[`../assets/lanyards/scenes/${n}-band.svg`];
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
    <img class="l z far" src={L('cr-facets')} alt="" /><i class="halo"></i>{#if !wide}<span class="prw"><i class="prism"></i></span>{/if}
    <!-- round 6 (owner: push it a bit further): the prism's spectrum fanning from behind the medallion, glints on the facets -->
    {#if wide}<img class="l z near spec" src={L('cr-spectrum')} alt="" />
      <!-- round 7 (owner: round 6's card is better overall, the new diamond looks cool: both): a round brilliant in 3D hangs
           under the medallion, set on its table; a star of light on its girdle now and then
           (.claude/reports/club-lanyards/round7/gen-r7-clubs.py) -->
      <img class="l z gem" src={L('cr-gem')} alt="" /><i class="spark"></i>{/if}
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
    <!-- the card (round 6, owner: round 5 was childish): an empty stage before the show, the house curtain's folds at the
         side, a grand piano lid up in one follow-spot, its light pooled on the boards. The badge's band: the stage with
         velvet, valance, a sound wave, their wordmark and the keys at the foot. Round 7 (owner: direction right, still
         mediocre): the stage drawn properly, a valance with its gold fringe across the top, the curtain tied back in gold,
         polished boards and the footlights' glow; the piano bigger and lacquered, its keys, the spot's rim light, dust in
         the beam -->
    {#if wide}<img class="l z far" src={L('ah-stage')} alt="" /><span class="spw"><i class="spot"></i></span><img class="l z near" src={L('ah-grand')} alt="" />
    {:else}<i class="velvet"></i><span class="spw"><i class="spot"></i></span><i class="pool"></i>
      <img class="l z far wave" src={L('ah-wave')} alt="" /><img class="l" src={L('ah-valance')} alt="" /><img class="word" src={arthouse} alt="" /><img class="keys" src={keys} alt="" />{/if}
  {:else if look === 'qairymdylyqkbtu'}
    <!-- a sunrise: the sun behind the hill, the three of them on it, warm light rising -->
    <img class="l z far" src={L('qa-sun')} alt="" /><i class="motes"></i>
    <img class="l" src={L('qa-hill')} alt="" /><span class="fig ppl"><img src={people} alt="" /></span>
  {:else if look === 'shadekbtu'}
    <!-- paper. The card (round 5, owner: their official logo, not our smear): their brush-lettered SHADE painted across
         the whole sheet, their line from the logo set small at the top; the brush itself is the medallion (OrgMedal).
         The badge's band: their red swept across it, the word in the middle -->
    <i class="paper"></i>
    <!-- round 5b (owner: both): round 4's red sweep across the card over round 5's brushed word in the paper -->
    <!-- round 7 (owner: loves it, a bit more beautiful; their own avatar in the medallion, OrgMedal): the paper lit warm
         from the top right, a printer's hairline frame inside the edge, a few flecks of their red where the brush flicked -->
    {#if wide}<i class="shlight"></i><img class="sw z" src={shadeWord} alt="" /><img class="l z near" src={L('sh-strokes')} alt="" /><i class="fleck z"></i><i class="frame"></i><span class="shtag">CREATIVE PEOPLE CLUB</span>
    {:else}<img class="l z near" src={L('sh-strokes')} alt="" /><img class="word" src={shadeWord} alt="" />{/if}
  {:else if look === 'choice'}
    <!-- Choice (round 5b, their logo): near-black navy, the gold of their shield; the badge's band: the whole emblem in the
         middle under the same light. The card, round 7g (the owner's pick from three concepts, "a real wow"): a Spartan
         helmet's horsehair crest, alone and huge, sweeping across the whole card in gold strands; Thermopylae's dawn
         softly behind it, the sky warming at the horizon over the pass's ridges; a soft darkening behind the name.
         Round 7h (owner: with the gold shield, one composition): the minted shield, whole, centred on the medallion
         (its boss) at the right, the crest sweeping from behind it (.claude/reports/club-lanyards/round7/gen-r7-clubs.py) -->
    {#if wide}<img class="l z far chc" src={L('ch-crest')} alt="" /><img class="l z chs" src={L('ch-shield')} alt="" />
    {:else}<i class="chrays z"></i><img class="che" src={chEmblem} alt="" />{/if}
  {:else if look === 'japanesecultureclub'}
    <!-- their own layers (round 5): the pink sky with its pale sun and their shanyrak far, petals drifting over it; their
         sakura is the card's top layer, over the photo and the strip (Hero). The badge's band (MyQr) as they asked: no
         logo in the middle, no sakura -->
    <img class="l z far jb" src={jccBack} alt="" /><i class="petals"></i>
  {:else if look === 'teentertainmentkbtu'}
    <!-- óte entertainment (new3 r2, owner: in the grammar of SITE, Shade, KMA, Geology; .claude/reports/club-lanyards/new3/
         gen-r2.py): their blush lit from the top right, the house curtain's folds as fine coral lines far, fading toward
         the name; the stage's boards in layers under the strip; a vintage microphone standing on them in a follow-spot,
         its pool of light, a few flecks of confetti in the beam, some falling. The badge's band: the curtain, the spot on
         their wordmark. Round 3 (owner: "not enough detail, not enough volume"): the same stage in depth, the back wall's
         light and the house curtain's lit folds, the beam in haze and bokeh, the floor in perspective with its sheen and
         footlights, a heavy valance with fringe and tassels, the side curtain tied back, the microphone's chrome and cast
         shadow, confetti in and out of focus -->
    {#if wide}<img class="l z far" src={L('ote-far')} alt="" /><img class="l" src={L('ote-ground')} alt="" /><img class="l z near" src={L('ote-arch')} alt="" />
      <img class="l z near otm" src={L('ote-mic')} alt="" />
    {:else}<img class="l" src={L('ote-stage')} alt="" /><img class="word otw" src={oteWord} alt="" />{/if}
    <i class="fall"></i>
  {:else if look === 'klubanimeshnikov'}
    <!-- the anime club (new3): their own ink-wash art with its red spider lilies at the edges, a lighter mist behind the
         name; red embers drifting up -->
    <img class="l z far anb" src={animeBack} alt="" /><i class="mist"></i><i class="ash"></i>
  {:else if look === 'kbtumag'}
    <!-- kbtu.mag (new3 r2, the same grammar): cream paper lit from the top right, a halftone screen far fading toward the
         name, the desk in layers under the strip; two issues leaning on each other (the cover a halftone portrait under
         their masthead) and an inkwell with its fountain pen. The badge's band: the screen, their wordmark. Round 3 (owner:
         the left and the middle empty): a page faint behind the name (justified columns and their rule, a pull-quote
         mark, the running head and folio, crop marks, the screen going on softly), a pencil and a coffee ring low on the
         desk -->
    <i class="paper"></i>
    {#if wide}<img class="l z far" src={L('mag-far')} alt="" /><img class="l z far" src={L('mag-detail')} alt="" /><img class="l" src={L('mag-ground')} alt="" /><img class="l z near" src={L('mag-issue')} alt="" />
    {:else}<img class="l" src={L('mag-page')} alt="" /><img class="word mgw" src={magWord} alt="" />{/if}
  {:else if SCN[look]}
    <!-- round 11 (owner, Nov 6: round 10 too simple; KMA and Geology are the bar), round 12 (owner: "better, but can be
         much better"; an art director's craft points; .claude/reports/club-lanyards/round12/gen/gen-r12.py): three depths,
         one hero each drawn big and fine in the space under the medallion, the area behind the text calm, light from the
         upper left, depth by overlap and tone, no bloom. Enactus: their phoenix rising clean over a low district at dawn,
         their origami bird folded big. Case: the deck's chart on the glass, the table, the laptop with the case's numbers,
         their folder. KNL: a grand tourer on a wet road at night, its reflection under it. Literature: shelves, the desk,
         a big open book with its page edges, a quill across it. Tumar: their ornament along the top, the stage, a dombra
         laid down with its bridge and two strings. Web3: the flag's sun, a network, the steppe, four glass blocks on one
         grid. Zhyly Zhurek: two cupped hands holding a coral heart with their flame. The badge's band: the far and mid
         layers, their mark on top -->
    {#if wide}<img class="l z far" src={L(SCN[look] + '-far')} alt="" /><img class="l" src={L(SCN[look] + '-mid')} alt="" /><img class="l z near" src={L(SCN[look] + '-near')} alt="" />
    {:else}<img class="l z far" src={L(SCN[look] + '-far')} alt="" /><img class="l" src={L(SCN[look] + '-mid')} alt="" /><img class="word bw {look}" src={MARK[look]} alt="" />{/if}
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
  /* a 320 px phone: the card is 52 px narrower and the text keeps its width; the stone and the shield shrink round the
     medallion's centre (40, 40 from the top right) so the role and the course line stay clear */
  @media (max-width: 359px) {
    .wide .gem, .wide .chs { transform-origin: calc(100% - 40px) 40px; scale: 0.88; }
    .wide .spark { right: 66px; top: 54px; }
  }
  .crystalkbtu:not(.wide) { background: radial-gradient(60% 80% at 50% 30%, rgba(140, 240, 255, 0.35), transparent 70%), linear-gradient(180deg, rgb(12, 62, 76), rgb(14, 70, 84)); }
  .halo { right: -37px; bottom: -4px; width: 160px; height: 132px; background: radial-gradient(closest-side, rgba(150, 245, 255, 0.5), transparent); }
  .sc:not(.wide) .halo { right: auto; left: 50%; bottom: -10px; margin-left: -80px; }
  /* a prism's glint: a soft band of split light crossing the card once every 9 s */
  .prw { position: absolute; inset: 0; overflow: hidden; -webkit-mask: linear-gradient(90deg, transparent 25%, black 60%); mask: linear-gradient(90deg, transparent 25%, black 60%); }
  .prism { left: -90px; top: -40px; width: 70px; height: calc(100% + 80px); transform: translateX(0) rotate(18deg); opacity: 0;
    background: linear-gradient(90deg, transparent, rgba(255, 150, 210, 0.22) 25%, rgba(255, 255, 255, 0.5) 45%, rgba(140, 240, 255, 0.3) 60%, rgba(255, 236, 150, 0.2) 75%, transparent);
    animation: crprism 9s 1.4s cubic-bezier(.45, 0, .3, 1) infinite; }
  @keyframes crprism { 0% { transform: translateX(0) rotate(18deg); opacity: 0; } 4% { opacity: 1; } 18% { opacity: 1; } 22%, 100% { transform: translateX(560px) rotate(18deg); opacity: 0; } }
  .spec { opacity: 0.9; }
  .gem { object-position: 100% 0; --z: 2; --zs: 1.03; } /* round the medallion: anchored to the top right, as Hero sets it */
  /* a star of light on the girdle (the generator's point 255, 71.9), now and then: grows, turns a little, fades */
  .spark { right: 71px; top: 58px; width: 28px; height: 28px; opacity: 0; --z: 2;
    background: radial-gradient(circle, rgb(255, 255, 255) 0 1.5px, rgba(200, 250, 255, 0.6) 3px, transparent 60%),
      linear-gradient(90deg, transparent 10%, rgba(255, 255, 255, 0.9) 50%, transparent 90%) center / 100% 1.2px no-repeat,
      linear-gradient(transparent 10%, rgba(255, 255, 255, 0.9) 50%, transparent 90%) center / 1.2px 100% no-repeat;
    animation: crspark 7s 2s ease-in-out infinite; }
  @keyframes crspark { 0%, 70% { opacity: 0; transform: scale(0.3) rotate(0deg); } 80% { opacity: 1; transform: scale(1) rotate(30deg); } 92%, 100% { opacity: 0; transform: scale(0.4) rotate(60deg); } }
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
  .spw { position: absolute; right: -40px; top: -20px; width: 200px; height: calc(100% - 20px); transform-origin: 50% 0; animation: ahspot 14s ease-in-out infinite alternate; }
  .spot { inset: 0; background: linear-gradient(180deg, rgba(255, 214, 150, 0.32), rgba(255, 200, 130, 0.12) 85%, transparent); clip-path: polygon(46% 0, 54% 0, 80% 100%, 20% 100%); }
  @keyframes ahspot { from { transform: rotate(-2.5deg); } to { transform: rotate(2.5deg); } }
  .sc:not(.wide) .spw { right: auto; left: 50%; margin-left: -100px; }
  .pool { left: 50%; bottom: 12px; width: 120px; height: 18px; margin-left: -60px; background: radial-gradient(closest-side, rgba(255, 210, 150, 0.45), transparent); } /* the band's */
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
  .shlight { inset: 0; background: radial-gradient(70% 90% at 92% 8%, rgba(255, 250, 238, 0.85), transparent 60%), radial-gradient(60% 60% at 0% 100%, rgba(150, 90, 50, 0.12), transparent 70%); }
  .fleck { inset: 0; --z: 3; background: radial-gradient(circle at 63% 30%, rgba(200, 0, 0, 0.75) 0 1.2px, transparent 1.8px), radial-gradient(circle at 66% 24%, rgba(200, 0, 0, 0.6) 0 0.8px, transparent 1.3px),
    radial-gradient(circle at 71% 34%, rgba(200, 0, 0, 0.5) 0 0.7px, transparent 1.2px), radial-gradient(circle at 58% 70%, rgba(200, 0, 0, 0.55) 0 1px, transparent 1.6px),
    radial-gradient(circle at 92% 64%, rgba(200, 0, 0, 0.6) 0 1.4px, transparent 2px), radial-gradient(circle at 95% 58%, rgba(200, 0, 0, 0.45) 0 0.7px, transparent 1.2px); }
  .frame { inset: 5px; border-radius: var(--r-m); box-shadow: inset 0 0 0 0.6px rgba(200, 0, 0, 0.28); }
  .shtag { position: absolute; left: 18px; top: 10px; display: flex; gap: 6px; font: 800 6.5px/1 var(--font-text); letter-spacing: 0.2em; color: rgb(200, 0, 0); opacity: 0.85; }
  .shadekbtu .word { top: 30px; height: 56px; }

  /* ---- Choice: their navy all but black, gold rays fanning from behind the medallion, a gold laurel round it ---- */
  .choice { background: radial-gradient(46% 80% at calc(100% - 45px) 30%, rgba(226, 188, 114, 0.26), transparent 70%), radial-gradient(70% 90% at 0% 0%, rgba(70, 80, 140, 0.28), transparent 62%),
    linear-gradient(160deg, rgb(30, 35, 64), rgb(20, 22, 35) 55%, rgb(7, 8, 15)); }
  .sc:not(.wide).choice { background: radial-gradient(60% 90% at 50% 0%, rgba(226, 188, 114, 0.26), transparent 70%), linear-gradient(180deg, rgb(30, 35, 64), rgb(20, 22, 35)); }
  .chc { object-position: 50% 50%; }
  .chs { object-position: 100% 0; --z: 1; --zs: 1.02; } /* round its medallion: anchored to the card's top right, as Hero sets it */
  .chrays { inset: -40px; --z: -3; opacity: 0.7; /* from behind the medallion (round 6: the laurel's centre) */
    background: repeating-conic-gradient(from 0deg at calc(100% - 85px) 80px, rgba(226, 188, 114, 0.12) 0deg 1.2deg, transparent 1.2deg 14deg);
    -webkit-mask: radial-gradient(70% 90% at calc(100% - 85px) 80px, black, transparent 75%); mask: radial-gradient(70% 90% at calc(100% - 85px) 80px, black, transparent 75%); }
  .sc:not(.wide) .chrays { background: repeating-conic-gradient(from 0deg at 50% 60%, rgba(226, 188, 114, 0.12) 0deg 1.2deg, transparent 1.2deg 14deg);
    -webkit-mask: radial-gradient(60% 90% at 50% 60%, black, transparent 75%); mask: radial-gradient(60% 90% at 50% 60%, black, transparent 75%); }
  .che { left: 50%; top: 14px; height: 100px; transform: translateX(-50%); filter: drop-shadow(0 6px 16px rgba(0, 0, 0, 0.5)); }
  .choice .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.08), transparent 65%); box-shadow: inset 0 1px 0 rgba(226, 188, 114, 0.35); }

  /* ---- Japanese Culture: their pink, their shanyrak top right (behind the QR on the card), sakura near ---- */
  .japanesecultureclub { background: rgb(224, 172, 190); }
  .jb { object-position: 100% 0; --z: -3; }
  .sc:not(.wide) .jb { left: auto; bottom: auto; width: 160%; height: 160%; object-position: 100% 0; } /* the badge's band nearer: their shanyrak big, the sun cut at the left (club, Nov 3) */
  .petals { left: -120px; top: -120px; width: calc(100% + 240px); height: calc(100% + 240px); background: url('../assets/lanyards/scenes/jcc-petals.svg') 0 0 / 120px 120px;
    opacity: 0.85; animation: jcpetal 24s linear infinite; }
  @keyframes jcpetal { to { transform: translate(120px, 120px); } } /* one tile down and to the right: the wind, no seam; raspberry as their drawn petals, the pale ones melted into the pink (club, Nov 3) */
  .japanesecultureclub .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.3), transparent 65%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), inset 0 0 0 1px rgba(90, 30, 60, 0.12); }

  /* ---- óte: their blush, lit from the top right ---- */
  .teentertainmentkbtu { background: radial-gradient(70% 90% at 100% 0%, rgba(255, 255, 255, 0.55), transparent 70%), linear-gradient(165deg, rgb(248, 235, 234), rgb(243, 224, 224) 55%, rgb(236, 206, 205)); }
  .otw { top: 26px; height: 60px; }
  /* round 5 (owner): the microphone and its spot stand in the card's middle, between the text and the medallion; a 320 px
     card has no middle to spare (its text runs to the medallion), so there they stand smaller under the medallion */
  .teentertainmentkbtu.wide { container-type: inline-size; }
  @container (max-width: 310px) { .otm { translate: 53px 0; scale: 0.62; transform-origin: calc(100% - 93px) calc(100% - 42px); } }
  /* confetti falling, a tile per period, kept off the text (to the right on the card) */
  .fall { left: 0; top: -120px; width: 100%; height: calc(100% + 120px); background: url('../assets/lanyards/scenes/ote-fall.svg') 0 0 / 120px 120px; opacity: 0.8;
    -webkit-mask: linear-gradient(90deg, transparent 45%, black 75%); mask: linear-gradient(90deg, transparent 45%, black 75%); animation: otfall 30s linear infinite; }
  .sc:not(.wide) .fall { -webkit-mask: linear-gradient(90deg, black, transparent 32% 68%, black); mask: linear-gradient(90deg, black, transparent 32% 68%, black); }
  @keyframes otfall { to { transform: translateY(120px); } }
  .teentertainmentkbtu .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.4), transparent 65%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7), inset 0 0 0 1px rgba(150, 50, 45, 0.12); }

  /* ---- the anime club: their art; the band shows its top, the lily at the left and the swirl ---- */
  .klubanimeshnikov { background: rgb(150, 150, 154); }
  .sc:not(.wide) .anb { object-position: 50% 0%; } /* above the painted-out strip's reflection */
  .mist { inset: 0; background: radial-gradient(42% 60% at 40% 38%, rgba(236, 236, 238, 0.5), transparent 75%); }
  .sc:not(.wide) .mist { display: none; }
  /* embers: their red specks rising and drifting, a tile per period */
  .ash { left: 0; top: 0; width: calc(100% + 90px); height: calc(100% + 90px); opacity: 0.8; animation: anash 20s linear infinite;
    background: radial-gradient(circle at 18% 22%, rgba(214, 40, 48, 0.9) 0 0.9px, transparent 1.5px), radial-gradient(circle at 62% 70%, rgba(192, 38, 45, 0.8) 0 1.2px, transparent 1.8px),
      radial-gradient(circle at 80% 30%, rgba(255, 255, 255, 0.8) 0 0.8px, transparent 1.4px), radial-gradient(circle at 40% 88%, rgba(214, 40, 48, 0.7) 0 0.7px, transparent 1.3px);
    background-size: 90px 90px;
    -webkit-mask: linear-gradient(90deg, black, transparent 30% 55%, black); mask: linear-gradient(90deg, black, transparent 30% 55%, black); }
  @keyframes anash { to { transform: translate(-90px, -90px); } }
  .klubanimeshnikov .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.2), transparent 65%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5), inset 0 0 0 1px rgba(0, 0, 0, 0.18); }

  /* ---- kbtu.mag: cream paper, lit from the top left ---- */
  .kbtumag { background: radial-gradient(70% 90% at 100% 0%, rgba(255, 250, 240, 0.7), transparent 70%), linear-gradient(160deg, rgb(243, 233, 219), rgb(234, 220, 203) 55%, rgb(224, 206, 184)); }
  .kbtumag .paper { opacity: 0.3; }
  .mgw { top: 24px; height: 62px; }
  .kbtumag .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.35), transparent 65%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7), inset 0 0 0 1px rgba(62, 10, 18, 0.12); }

  /* ---- round 11: the seven's grounds under their scenes; their marks on the band ---- */
  .enactuskbtu { background: radial-gradient(70% 90% at 100% 0%, rgba(80, 100, 230, 0.35), transparent 65%), linear-gradient(160deg, rgb(18, 26, 110), rgb(10, 15, 85) 55%, rgb(4, 7, 46)); }
  .caseclubkbtu { background: radial-gradient(70% 90% at 100% 0%, rgba(120, 140, 230, 0.28), transparent 65%), linear-gradient(160deg, rgb(28, 39, 102), rgb(17, 26, 75) 55%, rgb(8, 13, 41)); }
  .knlknolimits { background: linear-gradient(165deg, rgb(14, 36, 96), rgb(7, 26, 74) 55%, rgb(2, 10, 34)); }
  .literatureclub { background: radial-gradient(70% 90% at 100% 0%, rgba(255, 252, 246, 0.8), transparent 65%), linear-gradient(160deg, rgb(243, 237, 229), rgb(237, 230, 220) 55%, rgb(226, 216, 202)); }
  .tumarorchestrakbtu { background: radial-gradient(70% 90% at 100% 0%, rgba(230, 194, 122, 0.2), transparent 65%), linear-gradient(160deg, rgb(20, 56, 143), rgb(11, 36, 112) 55%, rgb(4, 17, 58)); }
  .web { background: radial-gradient(60% 80% at 100% 0%, rgba(255, 228, 92, 0.22), transparent 65%), linear-gradient(160deg, rgb(74, 163, 186), rgb(42, 127, 151) 55%, rgb(15, 70, 86)); }
  .zhylyzhurekkbtu { background: radial-gradient(70% 90% at 100% 0%, rgba(255, 255, 255, 0.6), transparent 65%), linear-gradient(160deg, rgb(251, 239, 234), rgb(246, 226, 220) 55%, rgb(237, 203, 196)); }
  .bw { filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.35)); }
  .bw.enactuskbtu { top: 30px; height: 50px; }
  .bw.caseclubkbtu { top: 16px; height: 90px; }
  .bw.knlknolimits { top: 12px; height: 84px; }
  .bw.literatureclub { top: 14px; height: 100px; filter: none; }
  .bw.tumarorchestrakbtu, .bw.web { top: 22px; height: 76px; }
  .bw.zhylyzhurekkbtu { top: 12px; height: 96px; filter: drop-shadow(0 4px 12px rgba(120, 40, 60, 0.25)); }
  .literatureclub .gloss, .zhylyzhurekkbtu .gloss { background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.35), transparent 65%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7), inset 0 0 0 1px rgba(107, 31, 31, 0.12); }

  /* still: no loop under reduced motion or power saving; each scene's resting frame is a whole picture */
  @media (prefers-reduced-motion: reduce) { .snow, .prism, .sun, .bub i, .win, .spw, .motes, .petals, .fall, .ash { animation: none; } .win { opacity: 0.6; } .spark { display: none; } }
  :global(html.lowfx) .snow, :global(html.lowfx) .prism, :global(html.lowfx) .sun, :global(html.lowfx) .bub i, :global(html.lowfx) .win,
  :global(html.lowfx) .spw, :global(html.lowfx) .motes, :global(html.lowfx) .petals, :global(html.lowfx) .fall, :global(html.lowfx) .ash { animation: none; }
  :global(html.lowfx) .win { opacity: 0.6; }
  :global(html.lowfx) .spark { display: none; }
</style>
