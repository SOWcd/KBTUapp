<script lang="ts">
  // Small status label. Tinted, never solid (clean pass): solid colour is reserved for the primary button.
  import type { Snippet } from 'svelte';
  let { tone = 'neutral', children }: { tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'onphoto'; children: Snippet } = $props();
</script>

<span class="chip {tone}">{@render children()}</span>

<style>
  .chip {
    display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 8px; border-radius: 7px;
    font: 650 11.5px/1 var(--font-text); letter-spacing: 0.01em; white-space: nowrap; flex: none;
  }
  .neutral { background: var(--surface-2); color: var(--text-2); }
  .accent { background: var(--accent-soft); color: var(--accent-text); }
  .success { background: var(--success-soft); color: var(--success-text); }
  .danger { background: var(--danger-soft); color: var(--danger-text); }
  .warning { background: var(--warning-soft); color: var(--warning-text); }
  .onphoto { background: rgba(10, 12, 22, 0.42); color: #fff; }
</style>
