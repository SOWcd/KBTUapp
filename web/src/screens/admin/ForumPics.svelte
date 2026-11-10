<script lang="ts">
  // A forum post's photos for the moderator deciding on it: small, in order; a tap shows them whole.
  import type { Media } from '../../lib/api';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';

  let { photos }: { photos: Media[] | undefined } = $props();
  const view = (i: number) => sheets.photos((photos ?? []).map((x, j) => ({ ...x, id: j + 1, by: null, mine: false, canDelete: false })), i);
</script>

{#if photos?.length}
  <span class="fp">{#each photos as p, i (i)}<button onclick={(e) => { e.stopPropagation(); view(i); }} aria-label={t('fc.photo')}><img src={p.thumb} alt="" loading="lazy" /></button>{/each}</span>
{/if}

<style>
  .fp { display: flex; gap: var(--s-1); flex-wrap: wrap; }
  button { width: 72px; height: 72px; border-radius: var(--r-s); overflow: hidden; background: var(--fill-2); flex: none; }
  img { width: 100%; height: 100%; object-fit: cover; display: block; }
</style>
