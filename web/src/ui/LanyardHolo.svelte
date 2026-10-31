<script lang="ts">
  // The strip at the bottom of a lanyard's card: whose badge it is and its number, each in its own colours (owner,
  // Oct 20: "the bottom is the same on every card"). The shimmer follows the tilt (--gx, set by `glass` above it).
  import type { Look } from '../lib/awards';

  let { look, no }: { look: Look; no: string } = $props();
</script>

<div class="holo {look}">
  {#if look === 'sower'}<b class="w sw">SOWER</b>
  {:else if look === 'studex'}<b class="w sx"><i>STUD</i>EX<svg class="sxar" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 13L12 2M6 2H12V8" /></svg></b>
  {:else if look === 'cheer'}<b class="w ch">✦ CHEERLEADING</b>
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
  .w { display: flex; align-items: center; gap: 7px; font: inherit; }
  /* StudEx (owner, Oct 31: the rainbow made it like every other lanyard; review: .claude/reports/studex-strip-review.md):
     a pearl strip, one light sliding with the tilt and a faint cool one slower behind it, their name as in their logo
     (STUD red, EX navy) with the logo's arrow rising off the X */
  .studex { color: rgb(23, 48, 100); background-image:
      linear-gradient(100deg, transparent 40%, rgba(255, 255, 255, 0.9) 50%, transparent 60%),
      linear-gradient(100deg, transparent 30%, rgba(200, 216, 255, 0.55) 50%, transparent 70%),
      linear-gradient(180deg, rgb(255, 255, 255), rgb(236, 239, 246));
    background-size: 260% 100%, 200% 100%, 100% 100%; background-position: calc(50% + var(--gx, 0) * 110%) 0, calc(50% + var(--gx, 0) * 40%) 0, 0 0;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.8), inset 0 -1px 2px rgba(23, 48, 100, 0.16), 0 4px 12px -6px rgba(0, 0, 0, 0.45); }
  .studex span { font-variant-numeric: tabular-nums; }
  .sxar { width: 11px; height: 11px; margin: -9px 0 0 -1px; fill: none; stroke: rgb(23, 48, 100); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
  .sower { background-image: linear-gradient(100deg, #fff 25%, #D9D9DE 40%, #fff 52%, #C9C9CF 62%, #fff 75%); color: #0A0A0A; }
  .sx { gap: 0; font: 900 16px/1 var(--font-display); letter-spacing: -0.03em; color: #173064; }
  .sx i { font-style: normal; color: rgb(214, 38, 27); }
  .sw { font: 900 13px/1 var(--font-display); letter-spacing: 0.34em; }
  .cheer { background-image: linear-gradient(100deg, #FFE7A3 10%, #FFC6E0 40%, #fff 55%, #FFE7A3 90%); color: #2E3258;
    box-shadow: 0 0 0 1px rgba(255, 200, 61, 0.6), 0 6px 18px -6px rgba(255, 95, 162, 0.6); }
  .ch { font: 700 11px/1 Georgia, 'Times New Roman', serif; letter-spacing: 0.2em; }
  .knights { background: repeating-linear-gradient(115deg, rgba(255, 255, 255, 0.08) 0 6px, transparent 6px 14px), linear-gradient(90deg, #1C4C94, #2F6BD0);
    color: #fff; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3); }
  .kn { font: italic 900 15px/1 var(--font-display); letter-spacing: 0.04em; }
  .moments { background-image: linear-gradient(100deg, #F2DEC8 15%, #E3A985 40%, #F6E7D6 55%, #C9C391 75%, #F2DEC8 90%); color: #3A2016;
    box-shadow: inset 0 0 0 1px rgba(58, 32, 22, 0.15); }
  .mo { font: 800 12px/1 var(--font-display); letter-spacing: 0.34em; }
  .faces { background-image: linear-gradient(100deg, #6E7BFF, #C04BFF 30%, #FF4F9A 55%, #FFA43D 80%, #6E7BFF); color: #fff;
    box-shadow: 0 6px 18px -6px rgba(200, 64, 255, 0.6); }
  .fa { font: italic 900 12px/1 var(--font-display); letter-spacing: 0.14em; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25); }
</style>
