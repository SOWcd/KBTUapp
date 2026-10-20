<script lang="ts">
  // The strip at the bottom of a lanyard's card: whose badge it is and its number, each in its own colours (owner,
  // Oct 20: "the bottom is the same on every card"). The shimmer follows the tilt (--gx, set by `glass` above it).
  import type { Look } from '../lib/awards';
  import KbtuMark from './KbtuMark.svelte';

  let { look, no }: { look: Look; no: string } = $props();
</script>

<div class="holo {look}">
  {#if look === 'sower'}<b class="w sw">SOWER</b>
  {:else if look === 'studex'}<b class="w sx"><i>STUD</i>EX</b>
  {:else if look === 'cheer'}<b class="w ch">✦ CHEERLEADING</b>
  {:else if look === 'knights'}<b class="w kn">KNIGHTS</b>
  {:else}<b class="w"><KbtuMark size={16} />KBTU APP</b>{/if}
  <span>№ {no}</span>
</div>

<style>
  .holo { position: relative; display: flex; align-items: center; justify-content: space-between; height: 28px; padding: 0 12px; border-radius: 9px;
    background: linear-gradient(100deg, #FFA6DA, #B9A3FF, #86E3FF, #A6FFD6, #FFE69A, #FFA6DA); background-size: 320% 100%;
    background-position: calc(50% + var(--gx, 0) * 60%) 0; color: rgba(14, 20, 48, 0.75); font: 800 10.5px/1 var(--font-text); letter-spacing: 0.16em; }
  .w { display: flex; align-items: center; gap: 7px; font: inherit; }
  .studex, .sower { background-image: linear-gradient(100deg, #fff 25%, #FFE1E6 40%, #E2E9FF 52%, #E6FFF4 60%, #fff 75%); color: #173064; }
  .sower { background-image: linear-gradient(100deg, #fff 25%, #D9D9DE 40%, #fff 52%, #C9C9CF 62%, #fff 75%); color: #0A0A0A; }
  .sx { gap: 0; font: 900 16px/1 var(--font-display); letter-spacing: -0.03em; color: #173064; }
  .sx i { font-style: normal; color: #CF3428; }
  .sw { font: 900 13px/1 var(--font-display); letter-spacing: 0.34em; }
  .cheer { background-image: linear-gradient(100deg, #FFE7A3 10%, #FFC6E0 40%, #fff 55%, #FFE7A3 90%); color: #2E3258;
    box-shadow: 0 0 0 1px rgba(255, 200, 61, 0.6), 0 6px 18px -6px rgba(255, 95, 162, 0.6); }
  .ch { font: 700 11px/1 Georgia, 'Times New Roman', serif; letter-spacing: 0.2em; }
  .knights { background: repeating-linear-gradient(115deg, rgba(255, 255, 255, 0.08) 0 6px, transparent 6px 14px), linear-gradient(90deg, #1C4C94, #2F6BD0);
    color: #fff; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3); }
  .kn { font: italic 900 15px/1 var(--font-display); letter-spacing: 0.04em; }
</style>
