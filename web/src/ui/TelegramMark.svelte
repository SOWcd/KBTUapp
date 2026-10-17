<script lang="ts">
  // Telegram's own plane (the telegram.org mark's), alone and in the text colour like every other icon, wherever a
  // button opens Telegram or sends into it (owner, Oct 7: the lucide plane "isn't Telegram's icon"; Oct 13: no blue
  // circle, one colour, "just an icon").
  let { size = 24 }: { size?: number } = $props();
  const PLANE = 'M54.3 118.8c35-15.2 58.3-25.3 70-30.2 33.3-13.9 40.3-16.3 44.8-16.4 1 0 3.2.2 4.7 1.4 1.2 1 1.5 2.3 1.7 3.3s.4 3.1.2 4.7c-1.8 19-9.6 65.1-13.6 86.3-1.7 9-5 12-8.2 12.3-7 .6-12.3-4.6-19-9-10.6-6.9-16.5-11.2-26.8-18-11.9-7.8-4.2-12.1 2.6-19.1 1.8-1.8 32.5-29.8 33.1-32.3.1-.3.1-1.5-.6-2.1-.7-.6-1.7-.4-2.5-.2-1.1.2-17.9 11.4-50.6 33.5-4.8 3.3-9.1 4.9-13 4.8-4.3-.1-12.5-2.4-18.7-4.4-7.5-2.4-13.5-3.7-13-7.9.3-2.2 3.3-4.4 8.9-6.7z';
</script>

<svg width={size} height={size} viewBox="42 57 136 136" aria-hidden="true" style="flex: none"><path fill="currentColor" d={PLANE} /></svg>
