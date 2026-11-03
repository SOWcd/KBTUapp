<script lang="ts">
  // A school's lanyard (Nov 2: their official shields and colours): its colour, a scene from its shield's own symbols
  // (assets/lanyards/schools, drawn by .claude/reports/school-lanyards/gen-schools.py), the shield itself as the figure:
  // on the card standing on the strip on the QR's axis, on the badge's band in the middle. The grammar of ClubScene:
  // far layers move with the tilt (base.css .z), one quiet loop at most, transform and opacity only, still under reduced
  // motion and power saving, paused with the card, static in the picker.
  import type { Look } from '../lib/awards';

  let { look, wide = false, qr = false }: { look: Look; wide?: boolean; qr?: boolean } = $props();
  const SC = import.meta.glob('../assets/lanyards/schools/*.svg', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
  const SH = import.meta.glob('../assets/lanyards/school-*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
  const L = (n: string) => SC[`../assets/lanyards/schools/${n}-${wide ? 'card' : 'band'}.svg`];
  // each school's layers, far to near ('far' moves with the tilt); a layer drawn for one framing only is skipped in the other.
  // Round 5 (owner: the left was empty, SEPI and Law plain): every card's art runs its whole width, quieter under the text
  const LAYERS: Record<string, [string, string][]> = {
    // round 5b (owner, Nov 3: Geology and KMA are the bar): one subject each under the medallion, with depth and its own
    // light (.claude/reports/school-lanyards/gen-r5b.py, card files only; the band keeps round 4's). Round 6 (owner, on
    // 5b): SITE a wafer, Business round 5's chart finished, ISE's left a world chart, SCE a molecule in 3D, SMSGT a wind
    // turbine at dawn, SSS an amphitheatre (.claude/reports/club-lanyards/gen-r6.py). Round 7 (owner, on 6: richer, "wow"):
    // BS a gold king on a board under the risen chart, SMSGT a solar field at dawn, SSS the theatre's colonnade against
    // the sun; then (7b) ISE a ring of light round the globe and the sunrise on its limb; (7d, owner: one card from the
    // variants) SITE the opened chip in front of a server aisle's light, fibre feeding it, SCE a distillation column at
    // night after rain; Law (owner: the portico "scanty, childish") a gavel on a leather-bound book in a lamp's light,
    // the library out of focus behind (.claude/reports/club-lanyards/round7/gen-schools-r7.py)
    site: [['site-traces', 'far'], ['site-aisle', 'far'], ['site-chip', 'near'], ['site-feed', 'near']], seogi: [['seogi-sky', 'far'], ['seogi-field', ''], ['seogi-dusk', 'far'], ['seogi-jack', 'near']],
    geology: [['geo-contours', 'far'], ['geo-strata', ''], ['geo-crystals', 'near']],
    business: [['bs-chart', 'far'], ['bs-board', ''], ['bs-king', 'near']],
    ise: [['ise-globe', 'far'], ['ise-chart', 'far'], ['ise-ring-back', 'far'], ['ise-earth', 'far'], ['ise-routes', 'near'], ['ise-ring-front', 'near']],
    kma: [['kma-moon', 'far'], ['kma-waves', 'waves'], ['kma-ship', 'near ship']],
    law: [['law-portico', 'far'], ['law-shelf', 'far'], ['law-desk', ''], ['law-book', 'near']], sam: [['sam-graph', 'far'], ['sam-ink', 'far'], ['sam-surface', 'near']],
    sce: [['sce-molecule-far', 'far'], ['sce-molecule', 'near'], ['sce-sky', 'far'], ['sce-plant', 'near']],
    smsgt: [['smsgt-comb', 'far'], ['smsgt-dawn', 'far'], ['smsgt-field', 'near']], sss: [['sss-book', 'far'], ['sss-sky', 'far'], ['sss-theatre', 'near']],
  };
  const shield = $derived(SH[`../assets/lanyards/school-${look}.webp`]);
</script>

<div class="sc {look}" class:wide class:qr aria-hidden="true">
  <i class="lit"></i>
  {#each (LAYERS[look] ?? []).filter(([n]) => L(n)) as [n, c] (n)}<img class="l {c}" class:z={c.includes('far') || c.includes('near')} src={L(n)} alt="" />{/each}
  {#if look === 'seogi'}<i class="embers"></i>{/if}
  {#if look === 'site'}<span class="sww"><i class="sweep"></i></span>{/if}
  <!-- the shield: on the card it is the medallion in the corner (Hero's OrgMedal, owner Nov 2), so the art has the side
       to itself; on the badge's band it stands whole in the middle -->
  {#if !wide}<span class="fig"><img src={shield} alt="" /></span>{/if}
  <i class="gloss"></i>
</div>

<style>
  .sc { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
  img { position: absolute; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  i { position: absolute; display: block; pointer-events: none; }
  .l { inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: 100% 100%; }
  .sc:not(.wide) .l { object-position: 50% 100%; }
  .far { --z: -2; --zs: 1.03; }
  /* a narrow card (320 px phones) keeps its width for the text: round 7's subjects stand smaller in their corner instead of
     sliding under the name (scale composes with .z's transform) */
  .sc.wide { container-type: inline-size; }
  @container (max-width: 310px) { :is(.sss, .sce, .ise, .business, .site, .smsgt, .law) .l { scale: 0.78; transform-origin: 100% 85%; } }
  .near { --z: 3; --zs: 1.03; }

  /* the badge's band: the shield whole, in the middle */
  .fig { position: absolute; left: 50%; bottom: 12px; width: 100px; height: 92px; margin-left: -50px; display: flex; justify-content: center; align-items: flex-end; }
  .fig img { position: static; height: 100%; max-width: 100%; object-fit: contain; filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.35)); }
  /* the light behind the shield */
  .lit { right: -60px; top: -40px; width: 240px; height: 200px; background: radial-gradient(closest-side, var(--lt, rgba(255, 255, 255, 0.22)), transparent); }
  .sc:not(.wide) .lit { right: auto; left: 50%; bottom: -30px; width: 260px; height: 180px; margin-left: -130px; }
  .gloss { inset: 0; border-radius: inherit; background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.14), transparent 65%), linear-gradient(180deg, transparent 65%, rgba(0, 0, 0, 0.14));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), inset 0 -2px 8px rgba(0, 0, 0, 0.22); }

  /* each school's ground: its official colour, lit from the top right */
  .site { background: radial-gradient(70% 90% at 100% 0%, rgba(80, 170, 240, 0.4), transparent 70%), linear-gradient(160deg, rgb(10, 100, 160), rgb(8, 91, 148) 50%, rgb(4, 50, 86)); --lt: rgba(245, 194, 66, 0.3); }
  /* SEPI: an oil field at dusk, the sky darkening up from the amber horizon */
  .seogi { background: linear-gradient(180deg, rgb(22, 20, 15), rgb(48, 36, 18) 45%, rgb(122, 76, 26) 74%, rgb(30, 26, 16)); --lt: rgba(255, 150, 60, 0.4); }
  .geology { background: radial-gradient(70% 70% at 90% 10%, rgba(230, 215, 160, 0.25), transparent 70%), linear-gradient(170deg, rgb(84, 112, 88), rgb(72, 100, 75) 50%, rgb(46, 66, 50)); --lt: rgba(240, 225, 170, 0.35); }
  .business { background: radial-gradient(70% 90% at 100% 0%, rgba(231, 200, 115, 0.2), transparent 70%), linear-gradient(160deg, rgb(44, 62, 104), rgb(35, 50, 83) 50%, rgb(18, 26, 46)); --lt: rgba(231, 200, 115, 0.3); }
  .ise { background: radial-gradient(70% 90% at 100% 100%, rgba(255, 120, 90, 0.35), transparent 70%), linear-gradient(160deg, rgb(232, 30, 18), rgb(200, 14, 6) 50%, rgb(120, 6, 2)); }
  .kma { background: radial-gradient(70% 60% at 85% 0%, rgba(120, 140, 255, 0.25), transparent 70%), linear-gradient(175deg, rgb(28, 32, 72), rgb(21, 24, 55) 55%, rgb(10, 12, 30)); }
  .law { background: radial-gradient(70% 90% at 30% 0%, rgba(255, 240, 210, 0.22), transparent 70%), linear-gradient(170deg, rgb(48, 80, 114), rgb(34, 60, 88) 50%, rgb(16, 30, 46)); }
  .sam { background: radial-gradient(70% 90% at 100% 0%, rgba(160, 210, 255, 0.25), transparent 70%), linear-gradient(160deg, rgb(64, 100, 132), rgb(53, 84, 112) 50%, rgb(30, 48, 66)); }
  .sce { background: radial-gradient(70% 90% at 100% 0%, rgba(200, 180, 255, 0.3), transparent 70%), linear-gradient(160deg, rgb(110, 84, 158), rgb(93, 68, 136) 50%, rgb(52, 36, 80)); }
  .smsgt { background: radial-gradient(70% 90% at 100% 0%, rgba(150, 240, 180, 0.25), transparent 70%), linear-gradient(160deg, rgb(16, 122, 80), rgb(11, 101, 66) 50%, rgb(5, 56, 36)); }
  .sss { background: radial-gradient(70% 90% at 100% 0%, rgba(180, 230, 200, 0.2), transparent 70%), linear-gradient(160deg, rgb(56, 96, 82), rgb(44, 77, 66) 50%, rgb(24, 44, 38)); }

  /* SITE: a signal running across the traces now and then */
  .sww { position: absolute; inset: 0; overflow: hidden; -webkit-mask: linear-gradient(90deg, transparent 30%, black 65%); mask: linear-gradient(90deg, transparent 30%, black 65%); }
  .sweep { left: -80px; top: 0; bottom: 0; width: 60px; opacity: 0; background: linear-gradient(90deg, transparent, rgba(245, 194, 66, 0.28), transparent);
    animation: stsweep 8s 1.4s ease-in-out infinite; }
  @keyframes stsweep { 0% { transform: translateX(0); opacity: 0; } 5% { opacity: 1; } 25% { opacity: 1; } 32%, 100% { transform: translateX(500px); opacity: 0; } }
  /* SEPI: embers rising from the flare */
  .embers { left: 0; top: 0; width: 100%; height: calc(100% + 100px); background: url('../assets/lanyards/schools/seogi-embers.svg') 0 0 / 100px 100px;
    -webkit-mask: radial-gradient(22% 45% at 88% 30%, black, transparent); mask: radial-gradient(22% 45% at 88% 30%, black, transparent); animation: seember 20s linear infinite; }
  .sc:not(.wide) .embers { -webkit-mask: radial-gradient(22% 50% at 72% 35%, black, transparent); mask: radial-gradient(22% 50% at 72% 35%, black, transparent); }
  @keyframes seember { to { transform: translateY(-100px); } }
  /* KMA: the wheel far, the sea's lines swaying a little */
  .waves { animation: kmwave 10s ease-in-out infinite alternate; }
  /* the ship rides the swell: a slow rise and roll about its waterline, on the waves' beat (its tilt depth is .near's) */
  .ship { transform-origin: 55% 62%; animation: kmship 10s ease-in-out infinite alternate; }
  @keyframes kmship { from { rotate: -1.2deg; translate: 0 0.6px; } to { rotate: 1deg; translate: 0 -0.8px; } }
  @keyframes kmwave { from { transform: translateX(-5px); } to { transform: translateX(5px); } }

  @media (prefers-reduced-motion: reduce) { .sweep, .embers, .waves, .ship { animation: none; } }
  :global(html.lowfx) .sweep, :global(html.lowfx) .embers, :global(html.lowfx) .waves, :global(html.lowfx) .ship { animation: none; }
</style>
