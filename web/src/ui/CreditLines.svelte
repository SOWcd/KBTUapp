<script lang="ts">
  // A person's lines in "People of the app": what shipped, in our words, each under a quiet label of its kind.
  //   under  the kind the block's own label already names (the idea's author under "Idea"): such lines go without theirs
  import type { CreditItem, CreditKind } from '../lib/api';
  import { lineOf } from '../lib/credits';
  import { t } from '../lib/i18n/index.svelte';

  let { items, under }: { items: CreditItem[]; under?: CreditKind } = $props();
</script>

<span class="ln" role="list">
  {#each items as i, n (n)}
    <span class="li" role="listitem">{#if i.kind !== under}<span class="k">{t(`cr.kind.${i.kind}`)}</span>{/if}<span>{lineOf(i)}</span></span>
  {/each}
</span>

<style>
  /* spans: the lines sit inside a card that is one button */
  .ln { display: flex; flex-direction: column; gap: 10px; }
  .li { display: flex; flex-direction: column; gap: 3px; font: 450 var(--fs-body)/1.35 var(--font-text); letter-spacing: -0.008em; color: var(--text); overflow-wrap: anywhere; }
  .k { font: 600 var(--fs-micro)/1.3 var(--font-text); letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-3); }
</style>
