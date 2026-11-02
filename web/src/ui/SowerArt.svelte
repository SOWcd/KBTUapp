<script lang="ts">
  // The creator's card art (round 5b, owner: "redo everything"; lib/awards.ts SOWER picks the concept). One subject: a
  // guilloche rosette (a banknote's security print, .claude/reports/club-lanyards/sower/gen-rosette.py) spreading from the
  // seal in the corner, cut as a mask out of a material that moves with the tilt: holographic foil on black titanium, or
  // gold leaf on black lacquer. It fades under the text. `wide`: the profile's card (the seal is the medallion, top right);
  // else the badge's back (MyQr), the same corner.
  import { SOWER } from '../lib/awards';
  import rosette from '../assets/lanyards/sower-rosette.svg?url';
  let { wide = false }: { wide?: boolean } = $props();
</script>

<div class="sa {SOWER}" class:wide aria-hidden="true" style="--ros: url({rosette})">
  <i class="tex"></i>
  <span class="fade"><i class="ros z"></i><i class="ros2 z"></i></span>
  {#if SOWER === 'gold'}<i class="rule"></i>{/if}
  <i class="sheen"></i>
</div>

<style>
  .sa { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; pointer-events: none; }
  i, .fade { position: absolute; display: block; pointer-events: none; }
  .fade { inset: 0; -webkit-mask: linear-gradient(100deg, transparent 22%, rgba(0, 0, 0, 0.5) 45%, black 70%); mask: linear-gradient(100deg, transparent 22%, rgba(0, 0, 0, 0.5) 45%, black 70%); }
  /* the rosette, centred on the seal (the medallion: 14 px in, 52 px: its centre 40 px from the top and the right) */
  .ros, .ros2 { right: -110px; top: -110px; width: 300px; height: 300px; -webkit-mask: var(--ros) center / contain no-repeat; mask: var(--ros) center / contain no-repeat; --z: -2; }
  .ros2 { right: -250px; top: -250px; width: 580px; height: 580px; opacity: 0.35; --z: -4; } /* a second, bigger, further: depth */
  .sa:not(.wide) .ros { right: -120px; top: -120px; width: 330px; height: 330px; }

  /* holo: black titanium, brushed; the foil's hues slide across the rosette as the phone tilts */
  .holo { background: radial-gradient(80% 110% at 100% 0%, rgba(120, 130, 170, 0.18), transparent 60%), linear-gradient(160deg, rgb(27, 28, 33), rgb(11, 11, 14) 55%, rgb(0, 0, 0)); }
  .holo .tex { inset: 0; opacity: 0.6; background: repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.022) 0 1px, transparent 1px 3px); }
  .holo .ros, .holo .ros2 { background: linear-gradient(115deg, rgb(142, 197, 255), rgb(199, 166, 255) 17%, rgb(255, 179, 217) 33%, rgb(255, 230, 166) 50%, rgb(166, 255, 224) 67%, rgb(142, 197, 255) 83%, rgb(199, 166, 255)) 0 0 / 300% 300%;
    background-position: calc(50% + var(--gx, 0) * 60%) calc(50% + var(--gy, 0) * 40%); opacity: 0.75; }
  .holo .ros2 { opacity: 0.22; }
  .holo .sheen { inset: 0; background: linear-gradient(115deg, transparent 35%, rgba(200, 220, 255, 0.07) 45%, rgba(255, 200, 240, 0.07) 52%, transparent 62%) 0 0 / 260% 100%;
    background-position: calc(50% + var(--gx, 0) * 50%) 0; }

  /* gold: black lacquer, the rosette in gold leaf with a light running over it, a gold rule inset round the card */
  .gold { background: radial-gradient(80% 110% at 100% 0%, rgba(120, 90, 30, 0.22), transparent 60%), linear-gradient(160deg, rgb(21, 18, 12), rgb(7, 6, 4) 55%, rgb(0, 0, 0)); }
  .gold .ros, .gold .ros2 { background: linear-gradient(115deg, rgb(122, 82, 16) 20%, rgb(246, 217, 138) 40%, rgb(255, 244, 208) 48%, rgb(216, 167, 67) 56%, rgb(122, 82, 16) 80%) 0 0 / 260% 100%;
    background-position: calc(50% + var(--gx, 0) * 70%) 0; opacity: 0.8; }
  .gold .ros2 { opacity: 0.25; }
  .rule { inset: 6px; border-radius: inherit; box-shadow: inset 0 0 0 0.75px rgba(232, 196, 120, 0.55); }
  .gold .sheen { inset: 0; background: linear-gradient(115deg, transparent 38%, rgba(255, 230, 170, 0.06) 48%, transparent 58%) 0 0 / 260% 100%; background-position: calc(50% + var(--gx, 0) * 50%) 0; }
</style>
