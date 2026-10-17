<script lang="ts">
  // The emoji grid of every editor (event, club, a new club, Admin's new club): 11 and "+N" that opens the rest (the
  // 12th takes the button's cell, so no hole); the picked one always shows (an older pick no longer listed comes first).
  import { untrack } from 'svelte';
  import { PICK_EMOJI } from '../lib/emoji';
  import { haptic } from '../lib/tg';
  import { fold } from './fold';
  import Emoji from './Emoji.svelte';

  let { value = $bindable(), size = 28 }: { value: string; size?: number } = $props();
  const SHOWN = 11;
  const list = $derived(PICK_EMOJI.includes(value) ? PICK_EMOJI : [value, ...PICK_EMOJI]);
  // opened once, it stays open (a pick above doesn't fold it under the finger); a pick from below opens it from the start
  let all = $state(untrack(() => list.indexOf(value) >= SHOWN));
</script>

<div class="pick">
  <div class="emojis">
    {#each list.slice(0, all ? SHOWN + 1 : SHOWN) as e (e)}<button type="button" class:on={value === e} onclick={() => (value = e)} aria-label={e}><Emoji name={e} {size} /></button>{/each}
    {#if !all}<button type="button" class="more num" onclick={() => { haptic.tap(); all = true; }}>+{list.length - SHOWN}</button>{/if}
  </div>
  {#if all}
    <div class="emojis" transition:fold>
      {#each list.slice(SHOWN + 1) as e (e)}<button type="button" class:on={value === e} onclick={() => (value = e)} aria-label={e}><Emoji name={e} {size} /></button>{/each}
    </div>
  {/if}
</div>

<style>
  .emojis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; }
  .pick { display: flex; flex-direction: column; }
  .emojis + .emojis { padding-top: 6px; } /* inside the fold, so the gap opens with it */
  button { aspect-ratio: 1; border-radius: 14px; background: var(--surface-2); display: flex; align-items: center; justify-content: center;
    transition: transform var(--t-fast) var(--ease), box-shadow var(--t-fast); }
  button.on { box-shadow: inset 0 0 0 2px var(--accent); background: var(--accent-soft); }
  button:active { transform: scale(0.92); }
  .more { font: 700 15px/1 var(--font-text); color: var(--text-2); }
</style>
