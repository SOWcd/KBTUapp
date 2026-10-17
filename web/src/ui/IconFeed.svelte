<script lang="ts">
  // Feed page icon (the prototype's): a phone with a play mark — vertical full-screen posters.
  // Same props as the Lucide icons it sits next to.
  let { size = 24, strokeWidth = 2 }: { size?: number; strokeWidth?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="2.5" width="12" height="19" rx="3" /><path d="M10 10l4 2-4 2z" fill="currentColor" /></svg>
