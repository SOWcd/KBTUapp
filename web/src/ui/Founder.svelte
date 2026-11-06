<script lang="ts">
  // The Creator's seal: the app's colonnade (the icon's five columns) on a disc, in the creator's lanyard's colours (his
  // photo's graphite, the rim and the colonnade its white paper; owner, Nov 6: no holographic foil). By a name it opens
  // what it is (AwardSheet). `idea`: the same seal in the brand's blue, for the one who came up with the app.
  let { size = 16, idea = false }: { size?: number; idea?: boolean } = $props();
  const disc = $derived(idea ? ['rgb(111, 147, 255)', 'rgb(47, 91, 234)', 'rgb(20, 48, 127)'] : ['rgb(94, 94, 93)', 'rgb(46, 46, 46)', 'rgb(20, 20, 20)']);
  const id = $props.id(); // gradient ids per seal: a closed sheet's copy can't take the others' with it
</script>

<svg class="seal" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <defs>
    <radialGradient id="{id}d" cx="0.34" cy="0.22" r="0.9"><stop offset="0" stop-color={disc[0]} /><stop offset="0.55" stop-color={disc[1]} /><stop offset="1" stop-color={disc[2]} /></radialGradient>
    <linearGradient id="{id}r" x1="0.15" y1="0" x2="0.85" y2="1"><stop offset="0" stop-color="rgb(255, 255, 255)" /><stop offset="0.5" stop-color="rgb(156, 156, 156)" /><stop offset="1" stop-color="rgb(232, 232, 231)" /></linearGradient>
    <linearGradient id="{id}m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="rgb(255, 255, 255)" /><stop offset="1" stop-color="rgb(192, 193, 190)" /></linearGradient>
  </defs>
  <circle cx="16" cy="16" r="15.5" fill="url(#{id}d)" />
  <circle cx="16" cy="16" r="14.2" fill="none" stroke="url(#{id}r)" stroke-width={idea ? 1.1 : 1.4} />
  {#if !idea}<circle cx="16" cy="16" r="12.6" fill="none" stroke="rgb(255, 255, 255)" stroke-opacity="0.18" stroke-width="0.4" />{/if}
  <!-- KbtuMark's colonnade, centred -->
  <g fill="url(#{id}m)" transform="translate(6.76 8.08) scale(0.66)">
    <rect x="1" y="1.5" width="26" height="4" rx="1.5" /><rect x="2" y="7" width="3" height="11" rx="1.5" /><rect x="7.25" y="7" width="3" height="11" rx="1.5" />
    <rect x="12.5" y="7" width="3" height="11" rx="1.5" /><rect x="17.75" y="7" width="3" height="11" rx="1.5" /><rect x="23" y="7" width="3" height="11" rx="1.5" />
    <rect x="0" y="19.5" width="28" height="3" rx="1.5" />
  </g>
  {#if !idea}<ellipse cx="11" cy="7.5" rx="6" ry="2.6" transform="rotate(-28 11 7.5)" fill="rgb(255, 255, 255)" fill-opacity="0.12" />{/if}
</svg>

<style>
  .seal { flex: none; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35)); }
</style>
