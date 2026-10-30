<script lang="ts">
  // A status on a card or a row ("You're going", "Draft", "Full"): a soft tone, never solid (solid colour is the
  // primary button's); onphoto over a poster or a photo. Was ui/Chip (Oct 30): the same look.
  import type { Snippet } from 'svelte';
  let { tone = 'neutral', children }: { tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'onphoto'; children: Snippet } = $props();
</script>

<span class="chip {tone}">{@render children()}</span>

<style>
  .chip {
    display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 11px; border-radius: var(--r-full);
    font: 600 var(--fs-sub)/1 var(--font-text); white-space: nowrap; flex: none; /* one family (mockup v23): colour is the only variant */
  }
  .neutral { background: var(--surface-2); color: var(--text-2); }
  .accent { background: var(--accent-soft); color: var(--accent-text); }
  .success { background: var(--success-soft); color: var(--success-text); }
  .danger { background: var(--danger-soft); color: var(--danger-text); }
  .warning { background: var(--warning-soft); color: var(--warning-text); }
  .onphoto { background: rgba(10, 12, 22, 0.42); color: var(--on-accent); }
</style>
