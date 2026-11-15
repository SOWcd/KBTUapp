<script lang="ts">
  // Opal's prompt card: a grey glyph on the left, the title bold, one grey line, a muted pill on the right ("Enable").
  // The whole card does the pill's thing.
  import type { Component } from 'svelte';
  import Card from './Card.svelte';
  import Button from './Button.svelte';

  let { icon: Icon, title, text, action, onclick }: { icon?: Component<any>; title: string; text?: string; action: string; onclick: () => void } = $props();
</script>

<Card {onclick}>
  <span class="ac">
    {#if Icon}<span class="ic"><Icon size={22} strokeWidth={1.8} /></span>{/if}
    <span class="tx"><b>{title}</b>{#if text}<span>{text}</span>{/if}</span>
    <span class="pill"><Button kind="secondary" size="s" {onclick}>{action}</Button></span>
  </span>
</Card>

<style>
  .ac { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-3) 14px; }
  .ic { flex: none; display: grid; place-items: center; color: var(--text-2); }
  .tx { flex: 1 1 140px; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 700 var(--fs-card)/1.25 var(--font-text); letter-spacing: -0.01em; }
  .tx span { font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-2); }
  .pill { flex: none; margin-left: auto; }
</style>
