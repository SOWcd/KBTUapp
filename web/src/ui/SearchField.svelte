<script lang="ts">
  // A search box: the magnifier, the field, a clear button once something's typed. raised: on the page (a card's
  // look), else inside a sheet.
  import Search from '@lucide/svelte/icons/search';
  import X from '@lucide/svelte/icons/x';
  import { t } from '../lib/i18n/index.svelte';

  let { value = $bindable(''), placeholder, raised = false }: { value?: string; placeholder: string; raised?: boolean } = $props();
</script>

<label class="search" class:raised>
  <Search size={18} />
  <input bind:value {placeholder} aria-label={placeholder} type="search" enterkeyhint="search" autocomplete="off" />
  {#if value}<button onclick={() => (value = '')} aria-label={t('common.close')}><X size={16} /></button>{/if}
</label>

<style>
  .search { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .raised { background: var(--surface); box-shadow: var(--shadow-card); }
  input { flex: 1; min-width: 0; font: 500 var(--fs-body)/1 var(--font-text); color: var(--text); }
  input::placeholder { color: var(--text-3); }
  input::-webkit-search-cancel-button { display: none; }
  button { position: relative; display: flex; color: var(--text-3); padding: 4px; }
  button::after { content: ''; position: absolute; inset: -10px; } /* a 44 px target around the small cross */
</style>
