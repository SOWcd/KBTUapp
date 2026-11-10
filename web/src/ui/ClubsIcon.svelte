<script lang="ts">
  // Clubs: three people, one in front (owner, Nov 10: two read as "just a person" beside Profile). Drawn in lucide's own
  // grid and stroke so it sits in the nav and the capsule like the others; takes lucide's props.
  let { size = 24, strokeWidth = 2, class: cls = '' }: { size?: number; strokeWidth?: number; class?: string } = $props();
</script>

<svg class={cls} xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width={strokeWidth} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <circle cx="12" cy="7.5" r="3" /><path d="M6.5 20v-1.5a5.5 5.5 0 0 1 11 0V20" />
  <circle cx="4.5" cy="9.5" r="2.2" /><path d="M1.5 19v-.8a3.6 3.6 0 0 1 4.3-3.5" />
  <circle cx="19.5" cy="9.5" r="2.2" /><path d="M22.5 19v-.8a3.6 3.6 0 0 0-4.3-3.5" />
</svg>
