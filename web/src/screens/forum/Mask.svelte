<script lang="ts">
  // The anonymous writer's face: a real avatar (a solid disc, the mask drawn in text colour), seen in both themes
  // (a grey glyph on a grey disc was the weakest face on the page).
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  let { size = 32 }: { size?: number } = $props();
</script>

<span class="mask" style:width="{size}px" style:height="{size}px" aria-hidden="true"><VenetianMask size={Math.round(size * 0.56)} strokeWidth={2} /></span>

<style>
  .mask { flex: none; display: grid; place-items: center; border-radius: var(--r-full); background: var(--surface-3); color: var(--text); }
</style>
