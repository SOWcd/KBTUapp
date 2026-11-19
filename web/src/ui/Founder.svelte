<script lang="ts">
  // The Creator's seal: a flat tile like the app's icon, the colonnade (the icon's five columns) in graphite on white
  // (owner, Nov 19: the tile over the enamel coin; Nov 18: a graphite disc was barely seen on a lanyard's art). Under
  // dark letters the card turns it over (--seal-tile / --seal-mark, Hero's .ink). By a name a tap says what it is (Hero).
  // `idea`: the same tile in the brand's blue, for the one who came up with the app.
  let { size = 16, idea = false }: { size?: number; idea?: boolean } = $props();
</script>

<svg class="seal" class:idea width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
  <rect class="t" x="1" y="1" width="30" height="30" rx="8.5" />
  <!-- KbtuMark's colonnade, centred -->
  <g class="m" transform="translate(5.92 7.36) scale(0.72)">
    <rect x="1" y="1.5" width="26" height="4" rx="1.5" /><rect x="2" y="7" width="3" height="11" rx="1.5" /><rect x="7.25" y="7" width="3" height="11" rx="1.5" />
    <rect x="12.5" y="7" width="3" height="11" rx="1.5" /><rect x="17.75" y="7" width="3" height="11" rx="1.5" /><rect x="23" y="7" width="3" height="11" rx="1.5" />
    <rect x="0" y="19.5" width="28" height="3" rx="1.5" />
  </g>
</svg>

<style>
  .seal { flex: none; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.4)); }
  .t { fill: var(--seal-tile, rgb(255, 255, 255)); stroke: rgba(0, 0, 0, 0.16); stroke-width: 0.6; } /* the hairline: its edge on a white page */
  .m { fill: var(--seal-mark, rgb(30, 30, 30)); }
  .idea .m { fill: var(--seal-mark, rgb(47, 91, 234)); }
</style>
