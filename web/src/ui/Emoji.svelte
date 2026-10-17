<script lang="ts">
  // Fluent 3D emoji (MIT) — content only (posters, awards, live phrases), never as UI icons.
  let { name, size = 28, alt = '' }: { name: string; size?: number; alt?: string } = $props();
</script>

<img class="emoji" src={`emoji/${name}.webp`} {alt} width={size} height={size} decoding="async" draggable="false" />

<style>
  .emoji { flex: none; object-fit: contain; pointer-events: none; }
</style>
