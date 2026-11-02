<script lang="ts">
  // The mark in the middle of a badge's QR: the app's for KBTU and SOWER, else the club's own (owner, Oct 29),
  // the same art as its lanyard (ui/LanyardBand) on its colours.
  import { clubLook, type Look } from '../lib/awards';
  import KbtuMark from './KbtuMark.svelte';
  import panther from '../assets/lanyards/panther-mark.webp'; // white: a black head on navy is a blob this small
  import KnightsHelm from './KnightsHelm.svelte';
  import aperture from '../assets/lanyards/moments-aperture.svg?url';
  import facesMark from '../assets/lanyards/faces-mark.webp'; // their wordmark on its black (round 5: their logo, not the hands)

  let { look }: { look: Look } = $props();
  const club = $derived(clubLook(look)); // the template's clubs: their mark on their plate's colours (lookVars)
  const art = $derived(club ? club.mark : ({ cheer: panther, moments: aperture, faces: facesMark } as Partial<Record<Look, string>>)[look]);
</script>

<span class="appmark {look}" class:club={!!club}>
  {#if art}<img src={art} alt="" />
  {:else if look === 'knights'}<span class="helm"><KnightsHelm /></span>
  {:else if look === 'studex'}<svg viewBox="0 0 100 100"><path d="M8 92 L70 30 L56 22 L96 8 L82 48 L76 36 L14 98 Z" fill="#fff" /></svg>
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
  .club { background: linear-gradient(150deg, var(--p1), var(--p2)); }
</style>
