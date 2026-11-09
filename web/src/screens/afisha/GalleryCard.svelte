<script lang="ts">
  // The Afisha's way into the Gallery (owner, Nov 9): the freshest album photos on one wide card, a tap opens them all on
  // the album's own grid. Nothing to show or not a student: no card (the store has it before the tab opens).
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { data, galleryGone, loadGallery } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import Card from '../../ui/Card.svelte';

  const pics = $derived(data.gallery.slice(0, 4));
  function open() {
    void loadGallery(true);
    sheets.album(() => data.gallery, undefined, galleryGone, undefined, undefined, { title: t('gallery.title'), note: t('gallery.note') });
  }
</script>

{#if session.me?.student && pics.length}
  <div class="gallery">
    <Card onclick={open}>
      <span class="top"><b>{t('gallery.title')}</b><ChevronRight size={20} strokeWidth={2.2} /></span>
      <span class="pics" style:--n={pics.length}>
        {#each pics as p (p.id)}<img src={p.thumb} alt="" decoding="async" draggable="false" style:background-color={p.color ?? 'var(--surface-2)'} />{/each}
      </span>
    </Card>
  </div>
{/if}

<style>
  .gallery { margin-top: 22px; }
  .top { display: flex; align-items: center; justify-content: space-between; color: var(--text-3); }
  .top b { font: 700 var(--fs-card)/1.25 var(--font-text); letter-spacing: -0.01em; color: var(--text); }
  /* one row at a quarter of the width, however few photos there are (squares when there are four) */
  .pics { display: grid; grid-template-columns: repeat(var(--n), 1fr); gap: 4px; aspect-ratio: 4; margin-top: 12px; }
  .pics img { display: block; width: 100%; height: 100%; min-width: 0; object-fit: cover; border-radius: var(--r-xs); user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
</style>
