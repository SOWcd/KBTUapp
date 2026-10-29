<script lang="ts">
  // A text with its addresses tappable, opened by Telegram (a t.me link stays inside it); the parent's tap (a story's
  // next) doesn't fire.
  import { linked } from '../lib/social';
  import { openLink } from '../lib/tg';
  let { text }: { text: string } = $props();
  const parts = $derived(linked(text));
  const go = (e: MouseEvent, url: string) => { e.preventDefault(); e.stopPropagation(); openLink(url); };
</script>

{#each parts as p, i (i)}{#if p.url}<a href={p.url} onclick={(e) => go(e, p.url!)}>{p.s}</a>{:else}{p.s}{/if}{/each}

<style>
  a { color: var(--accent-text); text-decoration: none; overflow-wrap: anywhere; }
</style>
