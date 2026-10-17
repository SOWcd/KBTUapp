<script lang="ts">
  // Badge (SPEC §4.11): a one-off mark for a moment, shaped like an enamel pin — a rounded hexagon in a gold
  // rim — so it never reads as an achievement (a round medal with tiers) or a status (the mark by the name).
  import Emoji from './Emoji.svelte';
  let { emoji, color, size = 58 }: { emoji: string; color: string; size?: number } = $props();

  const id = 'pin' + Math.random().toString(36).slice(2, 8); // gradient ids are page-global
  const hex = (r: number) => [-90, -30, 30, 90, 150, 210]
    .map((d) => `${(50 + r * Math.cos((d * Math.PI) / 180)).toFixed(1)},${(50 + r * Math.sin((d * Math.PI) / 180)).toFixed(1)}`).join(' ');
</script>

<span class="pin" style="width:{size}px;height:{size}px">
  <svg viewBox="0 0 100 100" aria-hidden="true">
    <defs>
      <linearGradient id="{id}r" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#FFF3C4" /><stop offset=".42" stop-color="#C8962F" /><stop offset=".72" stop-color="#FFE29A" /><stop offset="1" stop-color="#A8721A" />
      </linearGradient>
      <radialGradient id="{id}g" cx=".32" cy=".2" r=".9">
        <stop offset="0" stop-color="#fff" stop-opacity=".42" /><stop offset=".6" stop-color="#fff" stop-opacity="0" />
      </radialGradient>
    </defs>
    <polygon points={hex(43)} fill="url(#{id}r)" stroke="url(#{id}r)" stroke-width="10" stroke-linejoin="round" />
    <polygon points={hex(35)} fill={color} stroke={color} stroke-width="7" stroke-linejoin="round" />
    <polygon points={hex(35)} fill="url(#{id}g)" />
  </svg>
  <span class="glyph"><Emoji name={emoji} size={Math.round(size * 0.5)} /></span>
</span>

<style>
  .pin { position: relative; flex: none; display: inline-flex; filter: drop-shadow(0 5px 7px rgba(0, 0, 0, 0.32)); }
  svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .glyph { position: relative; margin: auto; display: flex; }
</style>
