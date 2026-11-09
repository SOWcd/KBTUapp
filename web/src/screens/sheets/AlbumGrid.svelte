<script lang="ts">
  // Every photo of an event's album at once, as in the phone's Photos (owner, Nov 8): square thumbnails edge to edge,
  // 3 a row (4 on a wide screen), 2 px apart, in the album's own order. A tap opens the viewer at that photo, grown out
  // of its square; closing it shrinks back into the square it is on now (scrolled to it). Telegram's Back goes
  // viewer -> grid -> sheet; the grid's scroll stays where it was (it never leaves the page under the viewer).
  // The list is live (a getter): what the viewer removes or a new upload shows here as it happens.
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import Images from '@lucide/svelte/icons/images';
  import type { AlbumPhoto } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import Pane from '../../ui/Pane.svelte';
  import Button from '../../ui/Button.svelte';

  // title, note: the Afisha's Gallery uses this same grid under its own name, with one line over it
  let { overlay, list, onremove, ongone, add, adding = () => 0, title, note }: {
    overlay: Overlay; list: () => AlbumPhoto[]; onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>; ongone?: (p: AlbumPhoto) => void;
    add?: () => void; adding?: () => number; title?: string; note?: string;
  } = $props();

  const photos = $derived(list());
  let grid: HTMLDivElement;

  // the square a photo lives in: brought into view first, so the viewer closes into a place you can see
  function cell(p: AlbumPhoto): Element | null {
    const el = grid?.querySelector(`[data-id="${p.id}"]`);
    const r = el?.getBoundingClientRect();
    if (r && (r.top < 100 || r.bottom > innerHeight - 40)) el!.scrollIntoView({ block: 'center' }); // not under the capsule
    return el ?? null;
  }
  const view = (i: number) => sheets.photos(photos, i, onremove, ongone, cell);

  // a thumbnail fades in once it's decoded (a cached one too: its load may have fired before we listened)
  function fade(img: HTMLImageElement) {
    const on = () => img.classList.add('in');
    if (img.complete && img.naturalWidth) on(); else img.addEventListener('load', on, { once: true });
  }
</script>

<Pane {overlay} icon={Images} title={photos.length ? `${title ?? t('album.title')} · ${photos.length}` : (title ?? t('album.title'))}>
  {#if note}<p class="note t-foot">{note}</p>{/if}
  <!-- div[role=button], not button: Pane's swipe from the left edge starts anywhere but on a button -->
  <div class="grid" bind:this={grid}>
    {#each photos as p, i (p.id)}
      <div class="c" role="button" tabindex="0" data-id={p.id} style:background-color={p.color ?? 'var(--surface-2)'}
        onclick={() => view(i)} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); view(i); } }}>
        <img src={p.thumb} alt="" loading="lazy" decoding="async" draggable="false" use:fade />
      </div>
    {/each}
    {#each { length: adding() } as _, i (i)}<span class="c wait"></span>{/each}
  </div>
  {#if add}
    <div class="add"><Button kind="tinted" size="l" full disabled={adding() > 0} onclick={add}>{#snippet icon()}<ImagePlus size={18} />{/snippet}{t('album.addMine')}</Button></div>
  {/if}
</Pane>

<style>
  /* edge to edge, out of the page's gutters, as the phone's grid */
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; margin: 0 calc(-1 * var(--gutter)); }
  @media (min-width: 600px) { .grid { grid-template-columns: repeat(4, 1fr); } }
  .c { position: relative; aspect-ratio: 1; overflow: hidden; display: block; cursor: pointer; -webkit-tap-highlight-color: transparent;
    content-visibility: auto; contain-intrinsic-size: auto 125px; }
  .c img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0; transition: opacity 260ms ease-out;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
  .c img:global(.in) { opacity: 1; }
  .c:active img { opacity: 0.72; transition-duration: 0ms; }
  .c:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .wait { background: var(--surface-2); animation: g-wait 1.1s ease-in-out infinite; }
  @keyframes g-wait { 50% { opacity: 0.5; } }
  .add { margin-top: var(--s-4); }
  .note { margin-bottom: var(--s-3); color: var(--text-2); }
  @media (prefers-reduced-motion: reduce) { .c img { transition: none; } .wait { animation: none; } }
</style>
