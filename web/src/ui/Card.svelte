<script lang="ts">
  // A card for rich content only (an event, a club, a post); a list of things is Rows in a Group.
  // --surface, --r-l, 16 inside; a soft shadow in the light theme, none in the dark (never a hairline with a shadow).
  //   onclick   the whole card opens something (a press that gives; Enter and Space too). A card with buttons inside
  //             keeps them its own: they don't trigger the card
  import type { Snippet } from 'svelte';

  let { onclick, children }: { onclick?: () => void; children: Snippet } = $props();
  const key = (e: KeyboardEvent) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onclick?.(); } };
  const tap = (e: MouseEvent) => { if (!(e.target as Element).closest('button, a, input, label') || e.target === e.currentTarget) onclick?.(); };
</script>

{#if onclick}
  <div class="card tap" role="button" tabindex="0" onclick={tap} onkeydown={key}>{@render children()}</div>
{:else}
  <div class="card">{@render children()}</div>
{/if}

<style>
  .card { position: relative; padding: var(--s-4); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); text-align: left; }
  .tap { cursor: pointer; transition: transform 450ms var(--ease-bounce); }
  .tap:active:not(:has(button:active)) { transform: scale(0.98); transition-duration: 80ms; }
  .tap:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
