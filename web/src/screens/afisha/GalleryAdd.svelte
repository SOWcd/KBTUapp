<script lang="ts">
  // My photos into the Gallery (GALLERY; owner, Nov 11): chosen already (the grid's first square opened the phone's
  // picker), here is what goes up, where to, and Publish. They are up at once under my name with no check before, so
  // the sheet says whose name and who will see. "Where" is there only when an event's album takes my photos now: the
  // general feed, or that event. The sheet closes on Publish; the store puts them on the grid and uploads them.
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import type { Id } from '../../lib/api';
  import { data, postGallery } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { overlay, files }: { overlay: Overlay; files: File[] } = $props();

  const events = $derived(data.galleryPost?.events ?? []);
  let event = $state<Id | null>(null); // null: the general feed
  const previews = $derived(files.map((f) => URL.createObjectURL(f)));
  $effect(() => { const made = previews; return () => made.forEach((u) => URL.revokeObjectURL(u)); });

  function publish() {
    haptic.select();
    close(overlay.id);
    void postGallery(files, event ?? undefined);
  }
</script>

<Sheet {overlay} title={t('album.addMine')} icon={ImagePlus}>
  <div class="page">
    <div class="shots" class:one={files.length === 1}>
      {#each previews as src (src)}<img {src} alt="" draggable="false" />{/each}
    </div>
    {#if events.length}
      <Group caption={t('gallery.where')}>
        <Row dense title={t('gallery.general')} accessory="check" checked={event === null} onclick={() => { haptic.select(); event = null; }} />
        {#each events as e (e.id)}
          <Row dense title={e.title} accessory="check" checked={event === e.id} onclick={() => { haptic.select(); event = e.id; }} />
        {/each}
      </Group>
    {/if}
    <p class="fs-sub faint fine">{t('gallery.asName', { name: session.me?.name ?? '' })}</p>
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full onclick={publish}>{t('gallery.publish')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  /* one photo: itself, whole; several: a row to scroll */
  .shots { display: flex; gap: 6px; width: 100%; overflow-x: auto; scrollbar-width: none; }
  .shots::-webkit-scrollbar { display: none; }
  .shots img { flex: none; width: 112px; height: 148px; object-fit: cover; border-radius: var(--r-s); display: block; }
  .shots.one { justify-content: center; }
  .shots.one img { width: auto; max-width: 100%; height: auto; max-height: 240px; border-radius: var(--r-m); }
  .fine { padding: 0 var(--s-4); text-align: center; }
</style>
