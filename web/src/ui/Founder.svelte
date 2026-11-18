<script lang="ts">
  // The Creator's seal: a white enamel coin, the app's colonnade (the icon's five columns) struck in graphite, a dark
  // edge round it (owner, Nov 18: the graphite disc was barely seen on a lanyard's art). White on a dark edge reads on
  // any picture, light or dark; the colours are his lanyard's (white paper, graphite). The staff's shields (ui/Shield)
  // are the same craft in metal: an edge, a field, a symbol struck in it. By a name a tap says what it is (Hero).
  // `idea`: the same coin struck in the brand's blue, for the one who came up with the app.
  let { size = 16, idea = false }: { size?: number; idea?: boolean } = $props();
  const edge = $derived(idea ? ['rgb(78, 118, 246)', 'rgb(20, 48, 127)'] : ['rgb(84, 84, 83)', 'rgb(14, 14, 14)']);
  const ink = $derived(idea ? ['rgb(47, 91, 234)', 'rgb(20, 48, 127)'] : ['rgb(58, 58, 57)', 'rgb(12, 12, 12)']);
  const id = $props.id(); // gradient ids per seal: a closed sheet's copy can't take the others' with it
</script>

<svg class="seal" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <defs>
    <linearGradient id="{id}e" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color={edge[0]} /><stop offset="1" stop-color={edge[1]} /></linearGradient>
    <radialGradient id="{id}f" cx="0.36" cy="0.24" r="0.9"><stop offset="0" stop-color="rgb(255, 255, 255)" /><stop offset="0.6" stop-color="rgb(244, 244, 242)" /><stop offset="1" stop-color="rgb(208, 209, 206)" /></radialGradient>
    <linearGradient id="{id}m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color={ink[0]} /><stop offset="1" stop-color={ink[1]} /></linearGradient>
  </defs>
  <circle cx="16" cy="16" r="15.6" fill="url(#{id}e)" />
  <circle cx="16" cy="16" r="13.7" fill="url(#{id}f)" />
  <!-- KbtuMark's colonnade, centred -->
  <g fill="url(#{id}m)" transform="translate(6.48 7.84) scale(0.68)">
    <rect x="1" y="1.5" width="26" height="4" rx="1.5" /><rect x="2" y="7" width="3" height="11" rx="1.5" /><rect x="7.25" y="7" width="3" height="11" rx="1.5" />
    <rect x="12.5" y="7" width="3" height="11" rx="1.5" /><rect x="17.75" y="7" width="3" height="11" rx="1.5" /><rect x="23" y="7" width="3" height="11" rx="1.5" />
    <rect x="0" y="19.5" width="28" height="3" rx="1.5" />
  </g>
</svg>

<style>
  .seal { flex: none; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.4)); }
</style>
