<script lang="ts">
  // Who wrote a thread (a face, or the mask for an anonymous one): a card's foot (small: the name alone) and the top of
  // its sheet (the topic and when it was written under the name).
  import type { Thread } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { noun } from '../../lib/forum';
  import Avatar from '../../ui/Avatar.svelte';
  import Mask from './Mask.svelte';

  let { th, tappable = false, small = false }: { th: Thread; tappable?: boolean; small?: boolean } = $props();
  const size = $derived(small ? 24 : 40);
</script>

<span class="who" class:small>
  {#if th.anon || !th.author}<Mask {size} />{:else}<Avatar person={th.author} {size} {tappable} />{/if}
  <span class="tx">
    <span class="nm"><b class="ellipsis">{th.anon || !th.author ? t('bd.anon') : th.author.name}</b>{#if th.mine}<i>· {t('bd.you')}</i>{/if}</span>
    {#if !small}<span class="meta">{noun(th.topic)} · {ago(th.createdAt)}</span>{/if}
  </span>
</span>

<style>
  .who { display: flex; align-items: center; gap: var(--s-3); min-width: 0; }
  .small { gap: var(--s-2); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  /* the name gives way to "· you", never the other way */
  .nm { display: flex; gap: 0.3em; min-width: 0; font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .small .nm { font-size: var(--fs-sub); color: var(--text-2); }
  .nm b { min-width: 0; font-weight: inherit; }
  .nm i { flex: none; font-style: normal; font-weight: 450; color: var(--text-3); }
  .meta { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
</style>
