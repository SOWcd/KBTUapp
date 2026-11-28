<script lang="ts">
  // A filter chip in a horizontal row (the forum's topics, Afisha's filters): 36 high, a quiet-fill capsule like Button s secondary; the selected
  // one tinted (accent-soft, accent text and icon), so it never outshines the one filled button.
  //   selected (aria-pressed), onclick
  //   icon     a lucide icon, monochrome (a topic's colour on a chip fails contrast: Board.svelte had to undo it)
  //   quiet    the secondary ink (a side door beside the main thing, the Forum tab's)
  //   full     the whole width of its cell, the words centred: a grid of choices (the forum composer's topics)
  // Put a row of them in a scroller with 4 px of block padding, or the 44 px hit areas get clipped.
  import type { Component, Snippet } from 'svelte';

  type Props = { selected?: boolean; quiet?: boolean; icon?: Component<any>; full?: boolean; onclick?: (e: MouseEvent) => void; children: Snippet };
  let { selected, quiet = false, icon: Icon, full = false, onclick, children }: Props = $props();
</script>

<button class="fc" class:on={selected} class:full class:quiet aria-pressed={selected} {onclick}>
  {#if Icon}<span class="ic"><Icon size={16} strokeWidth={2} /></span>{/if}{@render children()}
</button>

<style>
  /* quiet fill (the materials' third tier): a flat --fill body on solid ground, no rim, no fringe, no shadow. Glass is
     for what floats; a row of chips lies in the content and costs nothing to scroll */
  .fc { --body: var(--fill); position: relative; display: inline-flex; align-items: center; gap: 6px; height: var(--ctl-s); padding: 0 14px;
    border-radius: var(--r-full); flex: none; color: var(--text); font: var(--type-label); white-space: nowrap;
    background: linear-gradient(var(--body), var(--body)) var(--surface-solid);
    transition: color var(--t-base) var(--ease), transform var(--t-spring) var(--ease-bounce);
    -webkit-tap-highlight-color: transparent; }
  .fc::before { content: ''; position: absolute; inset: -4px 0; } /* 36 seen, 44 to the finger */
  .fc:active { transform: scale(0.965); transition-duration: var(--t-press); }
  .full { width: 100%; justify-content: center; }
  .quiet { color: var(--text-2); font-weight: 500; }
  .fc.on { --body: var(--accent-soft); color: var(--accent-text); }
  .ic { display: inline-flex; margin-left: -2px; }
  @media (hover: hover) { .fc:not(.on):hover { --body: var(--fill-2); } }
</style>
