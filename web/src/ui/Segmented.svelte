<script lang="ts" generics="T extends string | number">
  // A segmented switch (2-4 equal parts): a capsule track on --fill and a thumb that slides to the chosen part, 36 high,
  // the row's whole width. The thumb is the tab bar's lens (the one selected pill).
  //   items  { value, label }[];  value: bindable;  label: what it switches, for screen readers;  onchange
  import { fade } from 'svelte/transition';
  let { items, value = $bindable(), label, onchange }: { items: { value: T; label: string }[]; value: T; label?: string; onchange?: (v: T) => void } = $props();

  const at = $derived(items.findIndex((i) => i.value === value)); // -1: nothing chosen yet: no thumb; the first pick fades it in where it lands
  function pick(v: T) {
    if (v === value) return;
    value = v;
    onchange?.(v);
  }
</script>

<div class="sgm" role="radiogroup" aria-label={label} style:--n={items.length}>
  {#if at >= 0}<span class="thumb" in:fade={{ duration: 180 }} style:transform="translateX({at * 100}%)" aria-hidden="true"></span>{/if}
  {#each items as it (it.value)}
    <button role="radio" aria-checked={it.value === value} class:on={it.value === value} onclick={() => pick(it.value)}>{it.label}</button>
  {/each}
</div>

<style>
  .sgm { position: relative; display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); height: var(--ctl-s); padding: 2px;
    border-radius: var(--r-full); background: var(--fill); }
  /* the one selected pill (the tab bar's lens): a convex body lighter at the top, a rim lit from the glass's light side */
  .thumb { position: absolute; top: 2px; bottom: 2px; left: 2px; width: calc((100% - 4px) / var(--n)); border-radius: var(--r-full);
    background: linear-gradient(var(--lens-top), transparent 70%), var(--lens); box-shadow: var(--lens-shadow); transition: transform 380ms var(--ease-spring); }
  .thumb::after { content: ''; position: absolute; inset: 0; padding: 1px; border-radius: inherit; pointer-events: none;
    background:
      radial-gradient(ellipse 60% 150% at var(--hx, 24%) 0%, var(--lens-rim), transparent 72%),
      radial-gradient(ellipse 50% 140% at var(--ox, 76%) 100%, var(--lens-rim-low), transparent 72%);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude; }
  button { position: relative; min-width: 0; padding: 0 var(--s-2); border-radius: var(--r-full); color: var(--text-2);
    font: 600 var(--fs-sub)/1 var(--font-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center;
    transition: color var(--t-base) var(--ease); }
  button::after { content: ''; position: absolute; inset: -4px 0; } /* 44 to the finger */
  button:active { transform: none; opacity: 0.7; }
  button.on { color: var(--text); }
  @media (max-width: 359px) { button { padding: 0 4px; font-size: var(--fs-cap); } } /* 320 px: three labels with counts stay whole */
</style>
