<script lang="ts">
  // Opal's stats: a tiny grey caps label, the number big under it; the accent only on the key one. 2-4 side by side.
  //   items   { label, value, key? } ; key: the one number in the accent
  let { items }: { items: { label: string; value: string | number; key?: boolean }[] } = $props();
</script>

<dl class="stats" style:--n={items.length}>
  {#each items as s (s.label)}
    <div class="st"><dt>{s.label}</dt><dd class={["num", { key: s.key }]}>{s.value}</dd></div>
  {/each}
</dl>

<style>
  .stats { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: var(--s-3); margin: 0; }
  .st { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; text-align: center; }
  dt { max-width: 100%; font: 600 var(--fs-micro)/1.2 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  dd { margin: 0; font: 700 var(--fs-t1)/1.05 var(--font-display); letter-spacing: -0.03em; color: var(--text); }
  .key { color: var(--accent-text); }
</style>
