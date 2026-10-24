<script lang="ts">
  // Small status label. Tinted, never solid (clean pass): solid colour is reserved for the primary button.
  import type { Snippet } from 'svelte';
  let { tone = 'neutral', children }: { tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'onphoto'; children: Snippet } = $props();
</script>

<span class="chip {tone}">{@render children()}</span>

<style>
  .chip {
    display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 11px; border-radius: var(--r-full);
    font: 600 13px/1 var(--font-text); white-space: nowrap; flex: none; /* one family (mockup v23): colour is the only variant */
  }
  .neutral { background: var(--surface-2); color: var(--text-2); }
  .accent { background: var(--accent-soft); color: var(--accent-text); }
  .success { background: var(--success-soft); color: var(--success-text); }
  .danger { background: var(--danger-soft); color: var(--danger-text); }
  .warning { background: var(--warning-soft); color: var(--warning-text); }
  .onphoto { background: rgba(10, 12, 22, 0.42); color: #fff; }
</style>
