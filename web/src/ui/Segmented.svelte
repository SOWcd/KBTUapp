<script lang="ts" generics="T extends string | number">
  // A segmented switch (2-4 equal parts): a capsule track on --fill and a thumb that slides to the chosen part, 36 high,
  // the row's whole width. Replaces base.css .seg.
  //   items  { value, label }[];  value: bindable;  label: what it switches, for screen readers;  onchange
  let { items, value = $bindable(), label, onchange }: { items: { value: T; label: string }[]; value: T; label?: string; onchange?: (v: T) => void } = $props();

  const at = $derived(Math.max(0, items.findIndex((i) => i.value === value)));
  function pick(v: T) {
    if (v === value) return;
    value = v;
    onchange?.(v);
  }
</script>

<div class="sgm" role="radiogroup" aria-label={label} style:--n={items.length}>
  <span class="thumb" style:transform="translateX({at * 100}%)" aria-hidden="true"></span>
  {#each items as it (it.value)}
    <button role="radio" aria-checked={it.value === value} class:on={it.value === value} onclick={() => pick(it.value)}>{it.label}</button>
  {/each}
</div>

<style>
  .sgm { position: relative; display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); height: var(--ctl-s); padding: 2px;
    border-radius: var(--r-full); background: var(--fill); }
  .thumb { position: absolute; top: 2px; bottom: 2px; left: 2px; width: calc((100% - 4px) / var(--n)); border-radius: var(--r-full);
    background: var(--thumb); box-shadow: var(--shadow-thumb); transition: transform 380ms var(--ease-spring); }
  button { position: relative; min-width: 0; padding: 0 var(--s-2); border-radius: var(--r-full); color: var(--text-2);
    font: 600 var(--fs-sub)/1 var(--font-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center;
    transition: color var(--t-base) var(--ease); }
  button::after { content: ''; position: absolute; inset: -4px 0; } /* 44 to the finger */
  button:active { transform: none; opacity: 0.7; }
  button.on { color: var(--text); }
</style>
