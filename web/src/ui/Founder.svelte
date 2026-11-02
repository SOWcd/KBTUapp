<script lang="ts">
  // The Creator's seal: the app's colonnade (the icon's five columns) on a disc. Round 5b (owner: the old black-and-silver
  // one was weak), in the creator card's concept (lib/awards.ts SOWER): 'holo', a black titanium disc in an iridescent
  // rim, the colonnade in silver; 'gold', a gold coin with a reeded edge, the colonnade struck in black. By a name it opens
  // what it is (AwardSheet). `idea`: the same seal in the brand's blue, for the one who came up with the app.
  import { SOWER } from '../lib/awards';
  let { size = 16, idea = false }: { size?: number; idea?: boolean } = $props();
  const gold = $derived(!idea && SOWER === 'gold');
  const disc = $derived(idea ? ['rgb(111, 147, 255)', 'rgb(47, 91, 234)', 'rgb(20, 48, 127)'] : gold ? ['rgb(255, 243, 200)', 'rgb(216, 167, 67)', 'rgb(122, 82, 16)'] : ['rgb(58, 58, 66)', 'rgb(16, 16, 20)', 'rgb(0, 0, 0)']);
  const id = $props.id(); // gradient ids per seal: a closed sheet's copy can't take the others' with it
  const reed = Array.from({ length: 48 }, (_, i) => (i * Math.PI) / 24);
</script>

<svg class="seal" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <defs>
    <radialGradient id="{id}d" cx="0.34" cy="0.22" r="0.9"><stop offset="0" stop-color={disc[0]} /><stop offset="0.55" stop-color={disc[1]} /><stop offset="1" stop-color={disc[2]} /></radialGradient>
    {#if idea}
      <linearGradient id="{id}r" x1="0.15" y1="0" x2="0.85" y2="1"><stop offset="0" stop-color="rgb(255, 255, 255)" /><stop offset="0.5" stop-color="rgb(156, 156, 166)" /><stop offset="1" stop-color="rgb(230, 230, 236)" /></linearGradient>
    {:else if gold}
      <linearGradient id="{id}r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="rgb(255, 246, 216)" /><stop offset="0.5" stop-color="rgb(138, 94, 20)" /><stop offset="1" stop-color="rgb(242, 210, 122)" /></linearGradient>
    {:else}
      <!-- foil: the hues a hologram throws, round the rim -->
      <linearGradient id="{id}r" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="rgb(159, 212, 255)" /><stop offset="0.25" stop-color="rgb(210, 168, 255)" /><stop offset="0.5" stop-color="rgb(255, 184, 220)" /><stop offset="0.75" stop-color="rgb(255, 231, 168)" /><stop offset="1" stop-color="rgb(168, 255, 226)" /></linearGradient>
    {/if}
    <linearGradient id="{id}m" x1="0" y1="0" x2="0" y2="1">
      {#if gold}<stop offset="0" stop-color="rgb(42, 28, 5)" /><stop offset="1" stop-color="rgb(20, 13, 2)" />{:else}<stop offset="0" stop-color="rgb(255, 255, 255)" /><stop offset="1" stop-color="rgb(184, 188, 200)" />{/if}
    </linearGradient>
  </defs>
  <circle cx="16" cy="16" r="15.5" fill="url(#{id}d)" />
  {#if gold}
    <!-- the reeded edge of a coin, then a struck ring -->
    <g stroke="rgb(106, 70, 8)" stroke-opacity="0.55" stroke-width="0.5">{#each reed as a (a)}<path d="M{16 + 15.4 * Math.cos(a)} {16 + 15.4 * Math.sin(a)}L{16 + 14.2 * Math.cos(a)} {16 + 14.2 * Math.sin(a)}" />{/each}</g>
    <circle cx="16" cy="16" r="13.2" fill="none" stroke="rgb(90, 60, 6)" stroke-opacity="0.6" stroke-width="0.5" />
    <circle cx="16" cy="16" r="12.7" fill="none" stroke="rgb(255, 242, 196)" stroke-opacity="0.7" stroke-width="0.4" />
  {:else}
    <circle cx="16" cy="16" r="14.2" fill="none" stroke="url(#{id}r)" stroke-width={idea ? 1.1 : 1.6} />
    {#if !idea}<circle cx="16" cy="16" r="12.6" fill="none" stroke="rgb(255, 255, 255)" stroke-opacity="0.18" stroke-width="0.4" />{/if}
  {/if}
  <!-- KbtuMark's colonnade, centred -->
  <g fill="url(#{id}m)" transform="translate(6.76 8.08) scale(0.66)">
    <rect x="1" y="1.5" width="26" height="4" rx="1.5" /><rect x="2" y="7" width="3" height="11" rx="1.5" /><rect x="7.25" y="7" width="3" height="11" rx="1.5" />
    <rect x="12.5" y="7" width="3" height="11" rx="1.5" /><rect x="17.75" y="7" width="3" height="11" rx="1.5" /><rect x="23" y="7" width="3" height="11" rx="1.5" />
    <rect x="0" y="19.5" width="28" height="3" rx="1.5" />
  </g>
  {#if !idea && !gold}<ellipse cx="11" cy="7.5" rx="6" ry="2.6" transform="rotate(-28 11 7.5)" fill="rgb(255, 255, 255)" fill-opacity="0.12" />{/if}
</svg>

<style>
  .seal { flex: none; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35)); }
</style>
