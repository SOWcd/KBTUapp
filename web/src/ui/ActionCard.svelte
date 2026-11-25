<script lang="ts">
  // Opal's prompt, one compact row (a one-time ask never takes a screen's third): a grey glyph in a tile, one line,
  // a muted pill ("Enable"). The whole card does the pill's thing.
  import type { Component } from 'svelte';
  import Card from './Card.svelte';
  import Button from './Button.svelte';

  let { icon: Icon, title, action, onclick }: { icon?: Component<any>; title: string; action: string; onclick: () => void } = $props();
</script>

<div class="w">
<Card {onclick}>
  <span class="ac">
    {#if Icon}<span class="ic"><Icon size={20} strokeWidth={1.8} /></span>{/if}
    <b class="clamp-2">{title}</b>
    <Button kind="secondary" size="s" {onclick}>{action}</Button>
  </span>
</Card>
</div>

<style>
  .w { --card-pad: var(--s-3); }
  .ac { display: flex; align-items: center; gap: var(--s-3); }
  .ic { flex: none; display: grid; place-items: center; width: var(--ctl-s); height: var(--ctl-s); border-radius: var(--r-s); background: var(--fill); color: var(--text-2); }
  b { flex: 1; min-width: 0; font: 600 var(--fs-body)/1.25 var(--font-text); letter-spacing: -0.01em; }
</style>
