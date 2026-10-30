<script lang="ts">
  // A filter chip in a horizontal row (the forum's topics, Afisha's filters): 36 high, a capsule on --fill; the selected
  // one tinted (accent-soft, accent text and icon), so it never outshines the one filled button.
  //   selected (aria-pressed), onclick
  //   icon     a lucide icon, monochrome (a topic's colour on a chip fails contrast: Board.svelte had to undo it)
  // Put a row of them in a scroller with 4 px of block padding, or the 44 px hit areas get clipped.
  // A Chip without `selected` is a status label from before (Oct 30): it draws a Tag; use Tag.
  import type { Component, Snippet } from 'svelte';
  import Tag from './Tag.svelte';

  type Props = { selected?: boolean; icon?: Component<any>; onclick?: (e: MouseEvent) => void;
    tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'onphoto'; children: Snippet };
  let { selected, icon: Icon, onclick, tone, children }: Props = $props();
</script>

{#if selected === undefined}
  <Tag {tone}>{@render children()}</Tag>
{:else}
  <button class="fc" class:on={selected} aria-pressed={selected} {onclick}>
    {#if Icon}<span class="ic"><Icon size={16} strokeWidth={2} /></span>{/if}{@render children()}
  </button>
{/if}

<style>
  .fc { position: relative; display: inline-flex; align-items: center; gap: 6px; height: var(--ctl-s); padding: 0 14px; border-radius: var(--r-full); flex: none;
    background: var(--fill); color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text); white-space: nowrap;
    transition: background-color var(--t-base) var(--ease), color var(--t-base) var(--ease), transform 450ms var(--ease-bounce); }
  .fc::after { content: ''; position: absolute; inset: -4px 0; } /* 44 to the finger */
  .fc.on { background: var(--accent-soft); color: var(--accent-text); }
  .ic { display: inline-flex; margin-left: -2px; }
  @media (hover: hover) { .fc:not(.on):hover { background: var(--fill-2); } }
</style>
