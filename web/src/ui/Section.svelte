<script lang="ts">
  // A section of a screen or a sheet: one header style everywhere (a --fs-sec title, a grey count, "All ›" on the right),
  // then its content.
  //   title     the section's name;  count: how many (grey, after the title; 0 hides it)
  //   onmore    shows "All ›" (moreLabel to name it otherwise), which opens the whole list
  import type { Snippet } from 'svelte';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { t } from '../lib/i18n/index.svelte';

  let { title, count = 0, onmore, moreLabel, children }: { title: string; count?: number; onmore?: () => void; moreLabel?: string; children?: Snippet } = $props();
</script>

<section class="sec">
  <header class="hd">
    <h2 class="tt">{title}{#if count > 0}<span class="n num">{count}</span>{/if}</h2>
    {#if onmore}<button class="more" onclick={onmore}>{moreLabel ?? t('common.all')}<ChevronRight size={18} strokeWidth={2.2} /></button>{/if}
  </header>
  {#if children}{@render children()}{/if}
</section>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--s-3); }
  .hd { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-3); padding: 0 var(--s-1); }
  .tt { min-width: 0; font: 700 var(--fs-sec)/1.18 var(--font-display); letter-spacing: -0.018em; overflow-wrap: break-word; hyphens: auto; }
  .n { margin-left: 8px; font-weight: 450; color: var(--text-3); }
  .more { position: relative; flex: none; display: inline-flex; align-items: center; gap: 0; margin-right: -6px; color: var(--accent-text);
    font: 450 var(--fs-row)/1.2 var(--font-text); letter-spacing: -0.012em; }
  .more::after { content: ''; position: absolute; inset: -12px -4px; } /* 44 to the finger */
  .more:active { opacity: 0.5; transform: none; }
</style>
