<script lang="ts">
  // My photos into the Gallery (GALLERY; owner, Nov 11): chosen already (the Gallery's Add opened the phone's
  // picker), so they come first and large, each with an x to leave it out. Under them the two choices at a glance:
  // "Where" as one row (the general feed, or an event whose album takes my photos now; there only when one does) and,
  // for a photo of no event, its theme as four chips (chosen already when Add was tapped under that theme). They are
  // up at once under my name with no check before, so one line says whose name and who will see. The button says what
  // it waits for. The sheet closes on Publish; the store puts them in the feed and uploads them.
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import X from '@lucide/svelte/icons/x';
  import type { GalleryTopic, Id } from '../../lib/api';
  import { data, postGallery } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Chip from '../../ui/Chip.svelte';

  let { overlay, files, topic: first }: { overlay: Overlay; files: File[]; topic?: GalleryTopic } = $props();

  const events = $derived(data.galleryPost?.events ?? []);
  let event = $state<Id | null>(null); // null: the general feed
  const TOPICS: GalleryTopic[] = ['campus', 'study', 'life', 'other'];
  // svelte-ignore state_referenced_locally (what was chosen as the sheet opened; mine to change after)
  let topic = $state<GalleryTopic | null>(first ?? null);
  // svelte-ignore state_referenced_locally
  let shots = $state(files.map((file) => ({ file, src: URL.createObjectURL(file) })));
  $effect(() => () => shots.forEach((s) => URL.revokeObjectURL(s.src))); // as the sheet goes
  function leave(src: string) {
    shots = shots.filter((s) => s.src !== src);
    URL.revokeObjectURL(src);
    if (!shots.length) close(overlay.id);
  }
  const where = $derived([{ id: null as Id | null, title: t('gallery.general') }, ...events]);
  const ready = $derived(event !== null || !!topic);

  function publish() {
    haptic.select();
    close(overlay.id);
    void postGallery(shots.map((s) => s.file), event ?? undefined, event === null ? topic ?? undefined : undefined);
  }
</script>

<Sheet {overlay} title={t('album.addMine')} icon={ImagePlus}>
  <div class="page">
    <div class="shots n{Math.min(shots.length, 4)}">
      {#each shots as s (s.src)}
        <span class="shot"><img src={s.src} alt="" draggable="false" /><button class="x" aria-label={t('album.remove')} onclick={() => leave(s.src)}><X size={14} strokeWidth={2.6} /></button></span>
      {/each}
    </div>
    {#if events.length}
      <Group>
        <Row title={t('gallery.where')} value={where.find((w) => w.id === event)?.title}
          menu={where.map((w) => ({ label: w.title, checked: event === w.id, onselect: () => { event = w.id; } }))} />
      </Group>
    {/if}
    {#if event === null}
      <div class="topics" role="group" aria-label={t('gallery.topic')}>
        {#each TOPICS as k (k)}<Chip full selected={topic === k} onclick={() => { haptic.select(); topic = k; }}>{t(`gallery.t.${k}`)}</Chip>{/each}
      </div>
    {/if}
    <p class="fs-sub faint fine">{t('gallery.asName', { name: session.me?.name ?? '' })}</p>
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full disabled={!ready} onclick={publish}>{t(ready ? 'gallery.publish' : 'gallery.pickTopic')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  /* one to three: centred, as large as the row lets them; more: a row to scroll */
  .shots { display: flex; justify-content: center; gap: var(--s-2); width: 100%; }
  .shot { position: relative; flex: 1 1 0; min-width: 0; max-width: 200px; aspect-ratio: 4 / 5; border-radius: var(--r-m); overflow: hidden; background: var(--surface-2); }
  .shot img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .n1 .shot { flex: none; max-width: 100%; aspect-ratio: auto; }
  .n1 .shot img { width: auto; max-width: 100%; height: auto; max-height: 300px; object-fit: contain; }
  .n4 { justify-content: flex-start; overflow-x: auto; scrollbar-width: none; }
  .n4::-webkit-scrollbar { display: none; }
  .n4 .shot { flex: none; width: 124px; }
  .x { position: absolute; top: 6px; right: 6px; width: 24px; height: 24px; display: grid; place-items: center; border-radius: var(--r-full);
    background: rgba(4, 6, 16, 0.56); color: white; }
  .x::after { content: ''; position: absolute; inset: -10px; } /* 44 to the finger */
  .topics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
  .topics :global(.fc) { padding: 0; }
  .fine { padding: 0 var(--s-2); text-align: center; }
  @media (max-width: 350px) { .topics :global(.fc) { font-size: var(--fs-cap); letter-spacing: -0.015em; } }
</style>
