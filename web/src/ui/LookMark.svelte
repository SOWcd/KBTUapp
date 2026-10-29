<script lang="ts">
  // The mark in the middle of a badge's QR: the app's for KBTU and SOWER, else the club's own (owner, Oct 29),
  // the same art as its lanyard (ui/LanyardBand) on its colours.
  import type { Look } from '../lib/awards';
  import KbtuMark from './KbtuMark.svelte';
  import panther from '../assets/lanyards/panther.webp';
  import knights from '../assets/lanyards/knights.webp';
  import aperture from '../assets/lanyards/moments-aperture.svg?url';
  import hands from '../assets/lanyards/faces-hands.webp';

  let { look }: { look: Look } = $props();
  const art: Partial<Record<Look, string>> = { cheer: panther, knights, moments: aperture, faces: hands };
</script>

<span class="appmark {look}">
  {#if art[look]}<img src={art[look]} alt="" />
  {:else if look === 'studex'}<svg viewBox="0 0 100 100"><path d="M8 92 L70 30 L56 22 L96 8 L82 48 L76 36 L14 98 Z" fill="#fff" /></svg>
  {:else}<KbtuMark />{/if}
</span>

<style>
  img { width: 74%; height: 74%; object-fit: contain; pointer-events: none; }
  .sower { background: #0A0A0A; }
  .studex { background: linear-gradient(135deg, #DE3B2E, #A9271E); }
  .studex svg { width: 58%; }
  .cheer { background: radial-gradient(circle at 50% 80%, #5560C2, #1D2042); }
  .cheer img { width: 80%; height: 80%; }
  .knights { background: linear-gradient(150deg, #3A7BEA, #0D2A63); }
  .knights img { width: 86%; height: 86%; }
  .moments { background: linear-gradient(150deg, #C46D47, #6E3322); }
  .moments img { width: 66%; height: 66%; }
  .faces { background: radial-gradient(circle at 50% 100%, #C040FF, #07060B 75%); }
  .faces img { width: 90%; height: 90%; }
</style>
