<script lang="ts" generics="T">
  // The one sort control of every long list of people (lib/sort.svelte.ts): the current order in quiet words at the
  // end of the list's heading or of its filter row; a tap opens the pull-down with the list's orders. The pick is
  // remembered per list and the rows move in the same frame.
  //   list     the list's name (its remembered choice);  orders: what it can be sorted by, the default first
  import ArrowDownUp from '@lucide/svelte/icons/arrow-down-up';
  import { orderOf, setOrder, type Order } from '../lib/sort.svelte';
  import { t } from '../lib/i18n/index.svelte';
  import { haptic } from '../lib/tg';
  import { menu } from './menu';

  let { list, orders }: { list: string; orders: Order<T>[] } = $props();
  const now = $derived(orderOf(list, orders));
</script>

<button class="sort" aria-label="{t('sort.label')}: {t(now.label)}" aria-haspopup="menu" onclick={(e) => { haptic.tap();
  menu(e.currentTarget, orders.map((o) => ({ label: t(o.label), checked: o.id === now.id, onselect: () => setOrder(list, o.id) })), 'end'); }}>
  <ArrowDownUp size={14} strokeWidth={2.2} />{t(now.label)}
</button>

<style>
  .sort { position: relative; flex: none; display: inline-flex; align-items: center; gap: 5px; margin-left: auto; padding: 0 var(--s-1);
    font: 500 var(--fs-sub)/1.2 var(--font-text); letter-spacing: -0.006em; white-space: nowrap; color: var(--text-2); transition: opacity var(--t-fast); }
  .sort::after { content: ''; position: absolute; inset: -13px -6px; } /* 44 to the finger */
  .sort:active { opacity: 0.5; transform: none; }
</style>
