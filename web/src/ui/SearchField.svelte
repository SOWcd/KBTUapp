<script lang="ts">
  // The one search box (v1): a capsule on --fill, 44 high, the magnifier 18, a clear button once something's typed.
  //   value (bindable), placeholder
  //   legacy, raised: today's look (v0, a 16 px corner on --surface-2; raised: a card's look on the page) for the screens
  //   that haven't moved yet; gone once they have
  import Search from '@lucide/svelte/icons/search';
  import X from '@lucide/svelte/icons/x';
  import { t } from '../lib/i18n/index.svelte';

  let { value = $bindable(''), placeholder, raised = false, legacy = false }: { value?: string; placeholder: string; raised?: boolean; legacy?: boolean } = $props();
</script>

<label class="search" class:v0={legacy || raised} class:raised>
  <Search size={18} strokeWidth={legacy || raised ? undefined : 2} />
  <input bind:value {placeholder} aria-label={placeholder} type="search" enterkeyhint="search" autocomplete="off" />
  {#if value}<button onclick={() => (value = '')} aria-label={t('common.close')}><X size={16} strokeWidth={legacy || raised ? undefined : 2.2} /></button>{/if}
</label>

<style>
  .search { display: flex; align-items: center; gap: var(--s-2); height: var(--ctl-m); padding: 0 var(--s-3) 0 14px; border-radius: var(--r-full);
    background: var(--fill); color: var(--text-3); }
  input { flex: 1; min-width: 0; font: 450 var(--fs-row)/1 var(--font-text); letter-spacing: -0.012em; color: var(--text); }
  input::placeholder { color: var(--text-3); }
  input::-webkit-search-cancel-button { display: none; }
  button { position: relative; display: flex; color: var(--text-3); padding: 4px; }
  button::after { content: ''; position: absolute; inset: -10px; } /* a 44 px target around the small cross */
  /* v0 */
  .v0 { gap: 8px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface-2); }
  .v0 input { font: 500 var(--fs-body)/1 var(--font-text); letter-spacing: normal; }
  .raised { background: var(--surface); box-shadow: var(--shadow-card); }
</style>
