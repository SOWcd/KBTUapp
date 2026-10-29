<script lang="ts">
  // A thread's head, the same in the feed and in its sheet: who (a face, or the mask for an anonymous one), when it last
  // moved, its topic.
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import type { Thread } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { TOPIC_EMOJI } from '../../lib/forum';
  import Avatar from '../../ui/Avatar.svelte';
  import Emoji from '../../ui/Emoji.svelte';

  let { th, tappable = false }: { th: Thread; tappable?: boolean } = $props();
</script>

<header class="ph">
  {#if th.anon || !th.author}<span class="mask" aria-hidden="true"><VenetianMask size={20} /></span>
  {:else}<Avatar person={th.author} size={36} {tappable} />{/if}
  <span class="tx">
    <b class="ellipsis">{th.anon || !th.author ? t('bd.anon') : th.author.name}{#if th.mine}<i class="me"> · {t('bd.you')}</i>{/if}</b>
    <i>{ago(th.bumpedAt)}</i>
  </span>
  <span class="topic"><Emoji name={TOPIC_EMOJI[th.topic]} size={18} />{t(`bd.topic.${th.topic}`)}</span>
</header>

<style>
  .ph { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .mask { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2); color: var(--text-2); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .tx b { font: 650 14.5px/1.2 var(--font-text); }
  .tx i { font: 550 12px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .tx .me { color: var(--text-3); font-weight: 550; }
  .topic { flex: none; display: inline-flex; align-items: center; gap: 4px; height: 26px; padding: 0 9px 0 6px; border-radius: var(--r-full);
    background: var(--surface-2); font: 600 12px/1 var(--font-text); color: var(--text-2); }
</style>
