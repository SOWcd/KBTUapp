<script lang="ts">
  // One casting in the Clubs tab's "recruiting" strip (the list: data.svelte currentCastings): come, when, where.
  // A tap opens its post, the same way a club's page does.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import type { Post } from '../lib/api';
  import { t } from '../lib/i18n/index.svelte';
  import { castingStatus } from '../lib/posts';
  import { nameOf } from '../lib/short';
  import { sheets } from '../lib/state/sheets';
  import OrgLogo from './OrgLogo.svelte';

  let { post }: { post: Post } = $props();
  const open = () => sheets.stories([{ org: post.org, items: [{ post }], unread: false, cast: false }], 0);
</script>

{#if post.casting}
  <button class="cc" onclick={open}>
    <OrgLogo org={post.org} size={40} />
    <span class="tx">
      <b class="ellipsis">{t('casting.come')}</b>
      <small class="ellipsis">{nameOf(post.org)}</small>
      <small class="wh ellipsis">{castingStatus(post.casting)} · {post.casting.place}</small>
    </span>
    <span class="mk"><ChevronRight size={18} /></span>
  </button>
{/if}

<style>
  .cc { display: flex; align-items: center; gap: 12px; width: 100%; min-width: 0; padding: 12px 14px; border-radius: var(--r-l); background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); text-align: left; color: var(--text); }
  .cc:active { transform: scale(0.98); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 600 var(--fs-body)/1.25 var(--font-text); }
  .tx small { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .tx .wh { font-weight: 600; color: var(--accent-text); }
  .mk { flex: none; display: flex; color: var(--text-3); }
</style>
