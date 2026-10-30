<script lang="ts">
  // A gathering thread's "who's in", its own row on a card and in the thread: the faces, how many, and "I'm in" (never
  // on my own thread). Nobody in yet: no "0 going", only the button.
  import Check from '@lucide/svelte/icons/check';
  import type { Thread } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';

  let { th, onjoin, tappable = false }: { th: Thread; onjoin: () => void; tappable?: boolean } = $props();
</script>

{#snippet check()}<Check size={16} strokeWidth={2.4} />{/snippet}

<div class="gt">
  {#if th.joins}
    {#if th.joiners?.length}<span class="faces">{#each th.joiners.slice(0, 3) as p (p.id)}<Avatar person={p} size={24} {tappable} />{/each}</span>{/if}
    <span class="n">{tn('bd.going', th.joins)}</span>
  {/if}
  {#if !th.mine}
    <span class="go"><Button kind="tinted" size="s" on={th.joined} icon={th.joined ? check : undefined} onclick={onjoin}>{t(th.joined ? 'bd.inOn' : 'bd.inOff')}</Button></span>
  {/if}
</div>

<style>
  .gt { display: flex; align-items: center; gap: var(--s-2); min-height: var(--ctl-m); }
  .faces { flex: none; display: inline-flex; }
  /* a ring of the card's own colour, the faces just touching: the initials stay whole */
  .faces > :global(*) { box-shadow: 0 0 0 2px var(--surface-solid); border-radius: var(--r-full); }
  .faces > :global(*) + :global(*) { margin-left: -2px; }
  .n { min-width: 0; font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .go { flex: none; margin-left: auto; }
</style>
