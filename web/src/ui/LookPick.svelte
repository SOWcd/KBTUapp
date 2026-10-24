<script lang="ts">
  // A club's or an event's look, one picker for both (owner, Oct 24): the emoji grid, the colours under it. `lead` puts
  // a swatch of the caller's own first (the event's photo colour); no `emoji` binding hides the grid (a photo cover).
  import type { Snippet } from 'svelte';
  import EmojiPick from './EmojiPick.svelte';

  let { emoji = $bindable(), color = $bindable(), colors, size = 30, lead }:
    { emoji?: string; color: string; colors: readonly string[]; size?: number; lead?: Snippet } = $props();
</script>

<div class="look">
  {#if emoji !== undefined}<EmojiPick bind:value={emoji} {size} />{/if}
  <div class="colors" style="--n:{colors.length + (lead ? 1 : 0)}">
    {@render lead?.()}
    {#each colors as c (c)}<button type="button" class:on={color === c} style="--c:{c}" onclick={() => (color = c)} aria-label={String(colors.indexOf(c) + 1)}></button>{/each}
  </div>
</div>

<style>
  .look { display: flex; flex-direction: column; gap: 14px; }
  .colors { display: grid; grid-template-columns: repeat(min(var(--n), 7), 1fr); gap: 10px 8px; justify-items: center; }
  .colors :global(button) { width: 100%; max-width: 34px; aspect-ratio: 1; border-radius: 50%; background: var(--c); transition: transform var(--t-fast) var(--ease), box-shadow var(--t-fast); }
  .colors :global(button.on) { box-shadow: 0 0 0 3px var(--bg), 0 0 0 5px var(--accent); }
  .colors :global(button:active) { transform: scale(0.92); }
</style>
