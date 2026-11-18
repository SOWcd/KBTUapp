<script lang="ts">
  // A person's lines in "People of the app": what shipped, in our words, each with a small quiet mark of its kind.
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import Bug from '@lucide/svelte/icons/bug';
  import CodeXml from '@lucide/svelte/icons/code-xml';
  import type { CreditItem } from '../lib/api';
  import { lineOf } from '../lib/credits';
  import { t } from '../lib/i18n/index.svelte';

  let { items, center = false }: { items: CreditItem[]; center?: boolean } = $props();
  const MARK = { idea: Lightbulb, find: Bug, code: CodeXml } as const;
</script>

<span class="ln" class:center role="list">
  {#each items as i, n (n)}
    {@const Mark = MARK[i.kind]}
    <span class="li" role="listitem"><span class="mk" role="img" aria-label={t(`cr.kind.${i.kind}`)}><Mark size={14} strokeWidth={2} /></span><span>{lineOf(i)}</span></span>
  {/each}
</span>

<style>
  /* spans: the lines sit inside a row that is one button */
  .ln { display: flex; flex-direction: column; gap: 5px; }
  .li { display: flex; gap: 7px; font: 450 var(--fs-body)/1.3 var(--font-text); letter-spacing: -0.008em; color: var(--text-2); overflow-wrap: anywhere; }
  .mk { flex: none; display: inline-flex; height: 1.3em; align-items: center; color: var(--text-3); }
  .center { align-items: center; }
</style>
