<script lang="ts">
  // A red count (unread, requests): 18 high, white digits; over 99 reads "99+". n 0 draws nothing.
  let { n }: { n: number } = $props();
</script>

{#if n > 0}<span class="badge num">{n > 99 ? '99+' : n}</span>{/if}

<style>
  .badge { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; padding: 0 5px; border-radius: var(--r-full);
    background: var(--danger); color: var(--on-accent); font: 600 var(--fs-micro)/1 var(--font-text); flex: none; }
</style>
