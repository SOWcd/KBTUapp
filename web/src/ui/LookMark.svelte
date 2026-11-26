<script lang="ts">
  // The mark in the middle of a badge's QR: the app's for KBTU and SOWER, else the club's own,
  // the same art as its lanyard (ui/LanyardBand) on its colours.
  import { clubLook, lookArt, type Look } from '../lib/awards';
  import KbtuMark from './KbtuMark.svelte';
  import KnightsHelm from './KnightsHelm.svelte';

  // Offline tickets pass their saved image (null if missing), never the network asset.
  let { look, logo }: { look: Look; logo?: string | null } = $props();
  let failed = $state<string | null>();
  const art = $derived(logo === undefined ? lookArt(look) : logo);
  const img = $derived(art && art !== failed ? art : null);
  // Keep the app mark on its own plate when a club's image is unavailable, including on light club plates.
  const mark = $derived(img || look === 'knights' || look === 'studex' || look === 'sower' ? look : 'kbtu');
</script>

<span class={['appmark', mark, { club: !!clubLook(mark) }]}>
  {#if img}<img src={img} alt="" onerror={() => failed = img} />
  {:else if mark === 'knights'}<span class="helm"><KnightsHelm /></span>
  {:else if mark === 'studex'}<svg viewBox="0 0 100 100"><path d="M8 92 L70 30 L56 22 L96 8 L82 48 L76 36 L14 98 Z" fill="#fff" /></svg>
  {:else}<KbtuMark />{/if}
</span>

<style>
  img { width: 74%; height: 74%; object-fit: contain; pointer-events: none; }
  .sower { background: #0A0A0A; }
  .studex { background: linear-gradient(135deg, #DE3B2E, #A9271E); }
  .studex svg { width: 58%; }
  .cheer { background: radial-gradient(circle at 50% 70%, rgb(70, 77, 136), rgb(24, 26, 52)); }
  .cheer img { width: 78%; height: 78%; }
  .knights { background: linear-gradient(150deg, rgb(47, 107, 208), rgb(14, 42, 98)); }
  .helm { display: flex; width: 70%; height: 70%; } /* the helmet alone: the whole logo was a smudge this small */
  .helm :global(svg) { width: 100%; height: 100%; } /* not base.css's .appmark svg (64%) */
  .moments { background: linear-gradient(150deg, #C46D47, #6E3322); }
  .moments img { width: 66%; height: 66%; }
  .faces { background: #000; }
  .faces img { width: 100%; height: 100%; }
  .japanesecultureclub img { width: 70%; height: 70%; } /* their sakura alone (the loose petal cut off), a middle size: edge to edge is too much */
  .club { background: linear-gradient(150deg, var(--p1), var(--p2)); }
</style>
