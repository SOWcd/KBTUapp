<script lang="ts">
  // Who wrote a thread (a face, or the mask for an anonymous one) and when it last moved: a card's foot (small) and the
  // top of its sheet.
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import type { Thread } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import Avatar from '../../ui/Avatar.svelte';

  let { th, tappable = false, small = false }: { th: Thread; tappable?: boolean; small?: boolean } = $props();
  const size = $derived(small ? 22 : 40);
</script>

<span class="ph" class:small>
  {#if th.anon || !th.author}<span class="mask" style:--s="{size}px" aria-hidden="true"><VenetianMask size={small ? 13 : 20} /></span>
  {:else}<Avatar person={th.author} {size} {tappable} />{/if}
  <span class="tx">
    <b class="ellipsis">{th.anon || !th.author ? t('bd.anon') : th.author.name}{#if th.mine}<i class="me"> · {t('bd.you')}</i>{/if}</b>
    {#if !small}<i>{ago(th.bumpedAt)}</i>{/if}
  </span>
</span>

<style>
  .ph { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .ph.small { gap: 7px; }
  .mask { flex: none; width: var(--s); height: var(--s); border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 650 15px/1.2 var(--font-text); }
  .small .tx b { font: 600 13px/1.2 var(--font-text); color: var(--text-2); }
  .tx i { font: 500 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .tx .me { color: var(--text-3); font-weight: 550; }
</style>
