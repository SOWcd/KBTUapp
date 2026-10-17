<script lang="ts">
  // The KBTU colonnade, the app's mark: the guest card, the middle of a badge's QR. Takes the text colour.
  let { size = 38 }: { size?: number } = $props();
</script>

<svg viewBox="0 0 28 24" width={size} height={Math.round((size * 24) / 28)} aria-hidden="true"><g fill="currentColor"><rect x="1" y="1.5" width="26" height="4" rx="1.5" /><rect x="2" y="7" width="3" height="11" rx="1.5" /><rect x="7.25" y="7" width="3" height="11" rx="1.5" /><rect x="12.5" y="7" width="3" height="11" rx="1.5" /><rect x="17.75" y="7" width="3" height="11" rx="1.5" /><rect x="23" y="7" width="3" height="11" rx="1.5" /><rect x="0" y="19.5" width="28" height="3" rx="1.5" /></g></svg>
