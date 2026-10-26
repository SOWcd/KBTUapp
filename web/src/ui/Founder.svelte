<script lang="ts">
  // The Creator's seal (black and white): a glossy black disc, a silver rim and the app's colonnade, the same
  // five columns as the icon (the old one had four). By a name it opens what it is (AwardSheet). `idea`:
  // the same seal in the brand's blue, for the one who came up with the app (the idea was hers).
  let { size = 16, idea = false }: { size?: number; idea?: boolean } = $props();
  const disc = $derived(idea ? ['#6F93FF', '#2F5BEA', '#14307F'] : ['#3C3C44', '#121216', '#000']);
  const id = $props.id(); // gradient ids per seal: a closed sheet's copy can't take the others' with it
</script>

<svg class="seal" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <defs>
    <radialGradient id="{id}d" cx="0.34" cy="0.22" r="0.9"><stop offset="0" stop-color={disc[0]} /><stop offset="0.55" stop-color={disc[1]} /><stop offset="1" stop-color={disc[2]} /></radialGradient>
    <linearGradient id="{id}r" x1="0.15" y1="0" x2="0.85" y2="1"><stop offset="0" stop-color="#fff" /><stop offset="0.5" stop-color="#9C9CA6" /><stop offset="1" stop-color="#E6E6EC" /></linearGradient>
    <linearGradient id="{id}m" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" /><stop offset="1" stop-color="#C8CBD6" /></linearGradient>
  </defs>
  <circle cx="16" cy="16" r="15.5" fill="url(#{id}d)" />
  <circle cx="16" cy="16" r="13.7" fill="none" stroke="url(#{id}r)" stroke-width="1.1" />
  <!-- KbtuMark's colonnade, centred -->
  <g fill="url(#{id}m)" transform="translate(6.76 8.08) scale(0.66)">
    <rect x="1" y="1.5" width="26" height="4" rx="1.5" /><rect x="2" y="7" width="3" height="11" rx="1.5" /><rect x="7.25" y="7" width="3" height="11" rx="1.5" />
    <rect x="12.5" y="7" width="3" height="11" rx="1.5" /><rect x="17.75" y="7" width="3" height="11" rx="1.5" /><rect x="23" y="7" width="3" height="11" rx="1.5" />
    <rect x="0" y="19.5" width="28" height="3" rx="1.5" />
  </g>
</svg>

<style>
  .seal { flex: none; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35)); }
</style>
