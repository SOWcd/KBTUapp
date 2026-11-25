<script lang="ts">
  import type { TextEntity } from '../lib/api/types';
  import { t } from '../lib/i18n/index.svelte';
  import { richParts } from '../lib/richText';
  import { openLink } from '../lib/tg';

  let { text, entities }: { text: string; entities?: TextEntity[] | null } = $props();
  const parts = $derived(entities?.length ? richParts(text, entities) : [text]);
  let revealed = $state.raw<Set<object>>(new Set());
  const tags = { bold: 'strong', italic: 'em', underline: 'u', strike: 's', code: 'code', pre: 'code', blockquote: 'span' } as const;
</script>

{#snippet render(nodes: typeof parts)}
  {#each nodes as node, i (i)}
    {#if typeof node === 'string'}
      {node}
    {:else}
      {@const { kind, url } = node.mark}
      {#if kind === 'spoiler'}
        {#if revealed.has(node.mark)}
          {@render render(node.children)}
        {:else}
          <button type="button" class="spoiler" aria-label={t('news.revealSpoiler')} onclick={(e) => {
            e.stopPropagation();
            revealed = new Set([...revealed, node.mark]);
          }}><span aria-hidden="true">{node.text}</span></button>
        {/if}
      {:else if kind === 'text_link' || kind === 'url'}
        <a href={url} onclick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (url) openLink(url);
        }}>{@render render(node.children)}</a>
      {:else}
        <svelte:element this={tags[kind]} class={kind}>{@render render(node.children)}</svelte:element>
      {/if}
    {/if}
  {/each}
{/snippet}

<span class="rich">{@render render(parts)}</span>

<style>
  .rich { white-space: pre-wrap; overflow-wrap: anywhere; }
  a { color: var(--accent-text); pointer-events: auto; }
  .spoiler { max-width: 100%; border-radius: var(--r-xs); white-space: inherit; overflow-wrap: inherit; background: var(--surface-2); pointer-events: auto; }
  .spoiler span { filter: blur(5px); }
  .rich :global(.blockquote), .rich :global(.pre) { display: block; padding-inline: 0.5em; background: var(--surface-2); }
  .rich :global(.blockquote) { border-inline-start: 2px solid var(--accent-text); }
</style>
