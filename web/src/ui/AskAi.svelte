<script lang="ts">
  // "Ask AI" on a card (owner, Nov 2: no tab of its own, the assistant where the question comes up): opens it carrying
  // this card, its own suggestions first. Only with the assistant's switch (session.board), like the Afisha's sparkle.
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { sheets } from '../lib/state/sheets';
  import { session } from '../lib/state/session.svelte';
  import type { AskCtx } from '../lib/state/assistant.svelte';
  import { t } from '../lib/i18n/index.svelte';
  import { haptic } from '../lib/tg';

  let { ctx, hint }: { ctx: AskCtx; hint: string } = $props();
</script>

{#if session.board}
  <button class="ai" onclick={() => { haptic.tap(); sheets.assistant(ctx); }}>
    <span class="sp"><Sparkles size={17} strokeWidth={2.1} /></span>
    <span class="tx"><b>{t('as.askAi')}</b><i>{hint}</i></span>
    <ChevronRight size={18} />
  </button>
{/if}

<style>
  .ai { display: flex; align-items: center; gap: 12px; width: 100%; margin: 16px 0 4px; padding: 10px 12px 10px 10px; border-radius: var(--r-m);
    background: var(--surface-2); color: var(--text-3); text-align: left; transition: transform var(--t-fast) var(--ease); }
  .ai:active { transform: scale(0.99); }
  .sp { flex: none; display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: var(--accent-soft); color: var(--accent-text); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 650 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .tx i { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
</style>
