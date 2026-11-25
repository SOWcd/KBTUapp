<script lang="ts">
  // A filter chip in a horizontal row (the forum's topics, Afisha's filters): 36 high, a glass capsule like Button s secondary; the selected
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
  /* the same lens glass as Button's secondary s (design rule 6): spot, sheen and bevel over --body on solid ground, the
     theme's rim (--lg-*) and its lift; still light, no blur, so a long row of chips costs nothing to scroll */
  .fc { --body: var(--fill); position: relative; isolation: isolate; display: inline-flex; align-items: center; gap: 6px; height: var(--ctl-s); padding: 0 14px;
    border-radius: var(--r-full); flex: none; color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text); white-space: nowrap;
    background:
      radial-gradient(ellipse 40% 60% at 24% 0%, var(--lg-spot), transparent 70%),
      linear-gradient(180deg, var(--lg-sheen), transparent 60%),
      linear-gradient(var(--body), var(--body)) var(--surface-solid);
    box-shadow: var(--lg-bevel), var(--lg-lift);
    transition: color var(--t-base) var(--ease), transform 450ms var(--ease-bounce);
    -webkit-tap-highlight-color: transparent; }
  .fc::before { content: ''; position: absolute; inset: -4px 0; } /* 36 seen, 44 to the finger (::after is the rim) */
  .fc::after { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; padding: 1px;
    background:
      radial-gradient(ellipse 46% 140% at 24% 0%, var(--lg-rim-hi), transparent 72%),
      radial-gradient(ellipse 50% 130% at 76% 100%, var(--lg-rim-lo), transparent 75%),
      var(--lg-rim-base);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude; }
  .fc:active { transform: scale(0.965); transition-duration: 80ms; }
  .full { width: 100%; justify-content: center; }
  .quiet { color: var(--text-2); font-weight: 500; }
  .fc.on { --body: var(--accent-soft); color: var(--accent-text); }
  .ic { display: inline-flex; margin-left: -2px; }
  @media (hover: hover) { .fc:not(.on):hover { --body: var(--fill-2); } }
</style>
