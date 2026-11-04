<script lang="ts">
  // My words with the AI's quote marked (the exact piece that stopped them, server ai.explain); none, or not in them: plain.
  // Svelte escapes both: the model's words never become markup.
  let { text, quote = null }: { text: string; quote?: string | null } = $props();
  const at = $derived(quote ? text.indexOf(quote) : -1);
</script>

{#if quote && at >= 0}{text.slice(0, at)}<mark>{quote}</mark>{text.slice(at + quote.length)}{:else}{text}{/if}

<style>
  mark { padding: 1px 2px; border-radius: 0.25em; background: var(--warning-soft); color: inherit; box-shadow: inset 0 -1.5px 0 var(--warning);
    -webkit-box-decoration-break: clone; box-decoration-break: clone; animation: lit 600ms var(--ease) backwards; }
  @keyframes lit { from { background: transparent; box-shadow: inset 0 0 0 transparent; } }
  @media (prefers-reduced-motion: reduce) { mark { animation: none; } }
</style>
