<script lang="ts">
  // The strip at the bottom of a lanyard's card: whose badge it is and its number, each in its own colours (owner,
  // Oct 20: "the bottom is the same on every card"). The shimmer follows the tilt (--gx, set by `glass` above it).
  import { clubLook, type Look } from '../lib/awards';

  let { look, no }: { look: Look; no: string } = $props();
  const club = $derived(clubLook(look)); // the template's clubs: their word on their colours (lookVars)
</script>

<div class="holo {look}" class:club={!!club}>
  {#if club}<b class="w ch" class:long={club.strip.length > 12}>{club.strip}</b>
  {:else if look === 'sower'}<b class="w sw">SOWER</b>
  {:else if look === 'studex'}<b class="w sx"><i>STUD</i>EX</b>
  {:else if look === 'cheer'}<b class="w ch">CHEERLEADING</b>
  {:else if look === 'knights'}<b class="w kn">KNIGHTS</b>
  {:else if look === 'moments'}<b class="w mo">MOMENTS</b>
  {:else if look === 'faces'}<b class="w fa">FACES FAMILY</b>
  {:else}<b class="w">KBTU APP</b>{/if}
  <span>№ {no}</span>
</div>

<style>
  .holo { position: relative; display: flex; align-items: center; justify-content: space-between; height: 28px; padding: 0 12px; border-radius: 9px;
    background: linear-gradient(100deg, #FFA6DA, #B9A3FF, #86E3FF, #A6FFD6, #FFE69A, #FFA6DA); background-size: 320% 100%;
    background-position: calc(50% + var(--gx, 0) * 60%) 0; color: rgba(14, 20, 48, 0.75); font: 800 10.5px/1 var(--font-text); letter-spacing: 0.16em; }
  /* a long name gives way before the number does (round 5: JCC's motto ran into it at 320 px) */
  .w { display: flex; align-items: center; gap: 7px; min-width: 0; overflow: hidden; font: inherit; white-space: nowrap; }
  .holo > span { flex: none; margin-left: 10px; font-variant-numeric: tabular-nums; }
  .w.long { display: block; text-overflow: ellipsis; letter-spacing: 0.12em; }
  /* StudEx (owner, Oct 31: the rainbow made it like every other lanyard; review: .claude/reports/studex-strip-review.md):
     a pearl strip, one light sliding with the tilt and a faint cool one slower behind it, their name as in their logo
     (STUD red, EX navy); no arrow here: the card above has it (owner: two arrows read as a tautology) */
  .studex { color: rgb(23, 48, 100); background-image:
      linear-gradient(100deg, transparent 40%, rgba(255, 255, 255, 0.9) 50%, transparent 60%),
      linear-gradient(100deg, transparent 30%, rgba(200, 216, 255, 0.55) 50%, transparent 70%),
      linear-gradient(180deg, rgb(255, 255, 255), rgb(236, 239, 246));
    background-size: 260% 100%, 200% 100%, 100% 100%; background-position: calc(50% + var(--gx, 0) * 110%) 0, calc(50% + var(--gx, 0) * 40%) 0, 0 0;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.8), inset 0 -1px 2px rgba(23, 48, 100, 0.16), 0 4px 12px -6px rgba(0, 0, 0, 0.45); }
  .studex span { font-variant-numeric: tabular-nums; }
  /* SOWER: the white paper his photo's hand is cut from, one light sliding with the tilt, the name in graphite ink */
  .sower { color: rgba(30, 30, 30, 0.72); background: linear-gradient(100deg, transparent 38%, rgba(255, 255, 255, 0.7) 50%, transparent 62%) calc(50% + var(--gx, 0) * 120%) 0 / 260% 100% no-repeat,
    linear-gradient(180deg, rgb(242, 242, 240), rgb(222, 222, 219));
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7), inset 0 -1px 2px rgba(0, 0, 0, 0.14), 0 4px 12px -6px rgba(0, 0, 0, 0.6); }
  .sower .sw { color: rgb(30, 30, 30); }
  .sx { gap: 0; font: 900 16px/1 var(--font-display); letter-spacing: -0.03em; color: #173064; }
  .sx i { font-style: normal; color: rgb(214, 38, 27); }
  .sw { font: 900 13px/1 var(--font-display); letter-spacing: 0.34em; }
  /* Cheerleading: brushed gold, one specular sliding with the tilt (Knights' mechanism in their gold), their navy on it
     (5.5:1 on the darkest stop) */
  .cheer { background: linear-gradient(100deg, transparent 38%, rgba(255, 248, 228, 0.45) 50%, transparent 62%) calc(50% + var(--gx, 0) * 120%) 0 / 260% 100% no-repeat,
    linear-gradient(100deg, rgb(196, 154, 64), rgb(236, 204, 128) 50%, rgb(190, 148, 60));
    color: rgb(29, 32, 66); box-shadow: inset 0 0 0 1px rgba(255, 236, 190, 0.6), inset 0 -1px 2px rgba(70, 46, 0, 0.25), 0 4px 12px -6px rgba(0, 0, 0, 0.5); }
  .cheer span { font-variant-numeric: tabular-nums; }
  .ch { font: 800 11px/1 var(--font-display); letter-spacing: 0.2em; }
  /* Knights (round 5b): navy enamel in a gold rim, their name in gold leaf, one light sliding with the tilt */
  .knights { background: linear-gradient(100deg, transparent 38%, rgba(255, 236, 190, 0.2) 50%, transparent 62%) calc(50% + var(--gx, 0) * 120%) 0 / 260% 100% no-repeat,
    linear-gradient(180deg, rgb(26, 63, 134), rgb(11, 29, 68));
    color: rgba(232, 196, 120, 0.9); box-shadow: inset 0 0 0 1px rgba(232, 196, 120, 0.75), inset 0 1px 0 rgba(255, 236, 190, 0.35), 0 4px 12px -6px rgba(0, 0, 0, 0.5); }
  .kn { font: italic 900 15px/1 var(--font-display); letter-spacing: 0.04em; color: transparent; -webkit-background-clip: text; background-clip: text;
    background-image: linear-gradient(180deg, rgb(255, 240, 200), rgb(232, 196, 120) 55%, rgb(184, 137, 62)); }
  /* Moments (round 5b): a frame of colour negative, its amber base, sprocket holes along both edges, a light sliding */
  .moments { background: linear-gradient(100deg, transparent 38%, rgba(255, 240, 220, 0.35) 50%, transparent 62%) calc(50% + var(--gx, 0) * 120%) 0 / 260% 100% no-repeat,
    repeating-linear-gradient(90deg, rgba(42, 18, 9, 0.6) 0 4px, transparent 4px 9px) 0 2px / 100% 3px no-repeat,
    repeating-linear-gradient(90deg, rgba(42, 18, 9, 0.6) 0 4px, transparent 4px 9px) 0 calc(100% - 2px) / 100% 3px no-repeat, linear-gradient(100deg, rgb(238, 154, 72), rgb(201, 98, 42) 60%, rgb(224, 138, 62));
    color: rgb(42, 18, 9); box-shadow: inset 0 0 0 1px rgba(255, 220, 180, 0.4), 0 4px 12px -6px rgba(0, 0, 0, 0.5); }
  .mo { font: 800 12px/1 var(--font-display); letter-spacing: 0.34em; }
  /* Faces: black glass, their gradient in the name's letters and a thin line under the strip (white on their bright
     gradient was 3:1); the letters' gradient a tint lighter than the wordmark's, so its violet keeps 4.5:1 on black */
  .faces { background: linear-gradient(100deg, rgb(110, 123, 255), rgb(192, 75, 255) 30%, rgb(255, 79, 154) 55%, rgb(255, 164, 61) 80%) 0 100% / 100% 2px no-repeat, linear-gradient(180deg, rgb(30, 24, 42), rgb(12, 10, 18));
    color: rgba(255, 255, 255, 0.88); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14), 0 6px 18px -6px rgba(200, 64, 255, 0.6); }
  .fa { font: italic 900 12px/1 var(--font-display); letter-spacing: 0.14em; color: transparent; -webkit-background-clip: text; background-clip: text;
    background-image: linear-gradient(100deg, rgb(160, 170, 255), rgb(214, 140, 255) 30%, rgb(255, 135, 185) 60%, rgb(255, 190, 110)); }
  /* the template (CLUB_LOOKS): the strip in the club's two colours, one specular sliding with the tilt (Knights' and
     Cheer's mechanism), their word in its ink */
  .club { background: linear-gradient(100deg, transparent 38%, rgba(255, 255, 255, var(--hs, 0.45)) 50%, transparent 62%) calc(50% + var(--gx, 0) * 120%) 0 / 260% 100% no-repeat,
    linear-gradient(100deg, var(--h1), var(--h2) 50%, var(--h1)); color: var(--h3);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.5), inset 0 -1px 2px rgba(0, 0, 0, 0.18), 0 4px 12px -6px rgba(0, 0, 0, 0.45); }
  .club span { font-variant-numeric: tabular-nums; }
  /* Enactus (round 15, owner: the plain gold strip): their gold, deeper at the ends, a faint pattern of the phoenix's
     feathers pressed into it, a navy hairline under it; the specular slides as on every club's */
  .enactuskbtu { background:
      linear-gradient(100deg, transparent 38%, rgba(255, 252, 235, 0.55) 50%, transparent 62%) calc(50% + var(--gx, 0) * 120%) 0 / 260% 100% no-repeat,
      linear-gradient(rgb(6, 10, 70), rgb(6, 10, 70)) 0 100% / 100% 1.5px no-repeat,
      url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='26' height='28' viewBox='0 0 26 28'%3E%3Cg fill='none' stroke='%238A5A00' stroke-opacity='.3' stroke-width='.8' stroke-linecap='round'%3E%3Cpath d='M3 25C8 19 12 13 13 4'/%3E%3Cpath d='M6 21C4 18 4 15 5 13M8.4 17.4C6.4 14.6 6.6 11.6 8 9.6M10.4 13.4C9 10.6 9.6 8 11.2 6.4M6 21C9 20.6 11.4 19 12.8 17M8.4 17.4C11.2 16.6 13 14.8 14 12.6M10.4 13.4C12.6 12.4 13.8 10.6 14.2 8.6'/%3E%3C/g%3E%3C/svg%3E") 0 0 / 26px 28px,
      linear-gradient(100deg, rgb(214, 148, 12), rgb(255, 214, 84) 22%, rgb(255, 197, 33) 50%, rgb(255, 214, 84) 78%, rgb(214, 148, 12));
    box-shadow: inset 0 0 0 1px rgba(255, 240, 190, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.6), inset 0 -2px 3px rgba(6, 10, 70, 0.22), 0 4px 12px -6px rgba(0, 0, 0, 0.5); }
  /* new3 r2 (owner: the anime club's glossy red bar fought the ink wash): charcoal glass over their art, a fine red
     hairline at its edge and a red ink stroke under their name, the number in their red */
  .klubanimeshnikov { color: rgba(246, 242, 240, 0.95); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
    background: radial-gradient(38% 140% at 0% 50%, rgba(192, 38, 45, 0.5), transparent 70%), linear-gradient(180deg, rgba(30, 30, 33, 0.72), rgba(10, 10, 12, 0.82));
    box-shadow: inset 0 0 0 0.75px rgba(192, 38, 45, 0.85), inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 4px 12px -6px rgba(0, 0, 0, 0.6); }
  .klubanimeshnikov > span { color: rgb(236, 92, 98); }
  /* óte and kbtu.mag: their colours, matte (the specular dimmed, no white rim) */
  .teentertainmentkbtu, .kbtumag { --hs: 0.14; box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.22), inset 0 -1px 2px rgba(0, 0, 0, 0.16), 0 4px 10px -6px rgba(0, 0, 0, 0.4); }
  .club .ch { white-space: nowrap; }
</style>
