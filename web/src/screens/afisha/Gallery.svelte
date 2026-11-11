<script lang="ts">
  // The Gallery (owner's pick, Nov 11): the capsule names it, no large title. Two shelves, each with a clear end:
  // "Albums … All ›", the events' albums as cover cards in a strip (the third peeks in; a tap opens the event with its
  // album over it), and "Photos … Add", the one tinted control (GALLERY: pick, then GalleryAdd). Under it one segmented
  // control of themes and the feed: justified rows of one or two photos, each in its own shape, saying what it is from
  // and whose. A theme shows what the list already has in the same frame and asks the server for its first page.
  // `albums`: every album alone, two a row (the shelf's All).
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Images from '@lucide/svelte/icons/images';
  import Plus from '@lucide/svelte/icons/plus';
  import { onMount } from 'svelte';
  import type { AlbumPhoto, GalleryAlbum } from '../../lib/api';
  import { data, deleteGallery, galleryGone, loadGallery, loadGalleryTheme } from '../../lib/state/data.svelte';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { focusPos } from '../../lib/photo';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Button from '../../ui/Button.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Segmented from '../../ui/Segmented.svelte';

  let { overlay, albums = false }: { overlay: Overlay; albums?: boolean } = $props();

  const THEMES = ['all', 'events', 'campus', 'study', 'life'] as const; // "other" photos: under All alone
  type Theme = (typeof THEMES)[number];
  let theme = $state<Theme>('all');
  const shown = $derived(theme === 'all' ? data.gallery : data.gallery.filter((p) => (theme === 'events' ? !!p.event : p.topic === theme)));
  const asked = new Set<Theme>(['all']); // a plain Set: nothing draws from it
  function pick(v: Theme) {
    haptic.select();
    if (!asked.has(v) && v !== 'all') { asked.add(v); void loadGalleryTheme(v); }
  }
  // the whole feed as it opens, so the viewer swipes across all of it
  onMount(() => { if (!albums) void loadGallery(true); });
  // no large title here: the capsule says the name from the start (Pane hushes it as it mounts, after this runs once)
  $effect(() => { if (!albums && overlay.quiet) overlay.quiet = false; });

  // Justified rows: two photos share a row when it still stands tall enough for their captions, else one fills it.
  // A photo takes width by its own shape; a lone tall one is cut to 4:5 so it never outgrows the screen.
  const shape = (p: AlbumPhoto) => (p.w && p.h ? Math.min(2.2, Math.max(0.66, p.w / p.h)) : 1);
  const rows = $derived.by(() => {
    const out: { p: AlbumPhoto; i: number; ar: number }[][] = [];
    for (let i = 0; i < shown.length; i++) {
      const a = shape(shown[i]), b = i + 1 < shown.length ? shape(shown[i + 1]) : 9;
      if (a + b <= 2.7) { out.push([{ p: shown[i], i, ar: a }, { p: shown[i + 1], i: i + 1, ar: b }]); i++; }
      else out.push([{ p: shown[i], i, ar: Math.max(a, 0.8) }]);
    }
    return out;
  });
  const from = (p: AlbumPhoto) => p.event?.title ?? (p.topic && p.topic !== 'other' ? t(`gallery.t.${p.topic}`) : null);

  let feed = $state<HTMLDivElement>();
  // the photo's own tile: brought into view first, so the viewer closes into a place you can see
  function cell(p: AlbumPhoto): Element | null {
    const el = feed?.querySelector(`[data-id="${p.id}"]`);
    const r = el?.getBoundingClientRect();
    if (r && (r.top < 100 || r.bottom > innerHeight - 40)) el!.scrollIntoView({ block: 'center' });
    return el ?? null;
  }
  const remove = async (p: AlbumPhoto) => ((await deleteGallery(p)) ? shown : null);
  const view = (i: number) => sheets.photos(shown, i, data.galleryPost ? remove : undefined, galleryGone, cell);
  const key = (e: KeyboardEvent, go: () => void) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
  function fade(img: HTMLImageElement) {
    const on = () => img.classList.add('in');
    if (img.complete && img.naturalWidth) on(); else img.addEventListener('load', on, { once: true });
  }

  let picker = $state<HTMLInputElement>();
  function picked(e: Event) {
    const el = e.currentTarget as HTMLInputElement, files = [...(el.files ?? [])].slice(0, 10); // at once, as the store takes
    el.value = '';
    if (files.length) sheets.galleryAdd(files);
  }
</script>

{#snippet card(a: GalleryAlbum)}
  <button class="alb" style:background-color={a.cover.color ?? 'var(--surface-2)'} onclick={() => sheets.event(a.id, null, true)}>
    <img src={a.cover.thumb} alt="" loading="lazy" decoding="async" draggable="false" style:object-position={focusPos(a.cover)} />
    <span class="cap"><b class="ellipsis">{a.title}</b><em class="num">{tn('gallery.photos', a.n)}</em></span>
  </button>
{/snippet}

<Pane {overlay} icon={Images} title={t(albums ? 'gallery.albums' : 'gallery.title')} bare={!albums}>
  {#if albums}
    <div class="all">{#each data.galleryAlbums as a (a.id)}{@render card(a)}{/each}</div>
  {:else}
    {#if data.galleryAlbums.length}
      <div class="head">
        <h2 class="fs-t3">{t('gallery.albums')}</h2>
        <button class="more" onclick={() => sheets.gallery(true)}>{t('common.all')}<ChevronRight size={18} strokeWidth={2.2} /></button>
      </div>
      <div class="shelf hscroll">{#each data.galleryAlbums.slice(0, 8) as a (a.id)}{@render card(a)}{/each}</div>
    {/if}

    <div class="head photos">
      <h2 class="fs-t3">{t('album.title')}</h2>
      {#if data.galleryPost}<Button kind="tinted" size="s" onclick={() => picker?.click()}>{#snippet icon()}<Plus size={16} strokeWidth={2.4} />{/snippet}{t('album.add')}</Button>{/if}
    </div>
    <div class="themes"><Segmented items={THEMES.map((k) => ({ value: k, label: t(`gallery.t.${k}`) }))} bind:value={theme} label={t('gallery.topic')} onchange={pick} /></div>

    <!-- div[role=button], not button: Pane's swipe from the left edge starts anywhere but on a button -->
    <div class="feed" bind:this={feed}>
      {#each rows as row (row[0].p.id)}
        <div class="rowp">
          {#each row as { p, i, ar } (p.id)}
            {@const what = from(p)}
            <div class="ph" class:wait={p.pending} role="button" tabindex="0" data-id={p.id} style:--ar={ar} style:background-color={p.color ?? 'var(--surface-2)'}
              onclick={() => p.pending || view(i)} onkeydown={(e) => p.pending || key(e, () => view(i))}>
              <img src={p.thumb} alt="" loading="lazy" decoding="async" draggable="false" use:fade />
              {#if what || p.by}<span class="cap"><b class="ellipsis">{what ?? p.by}</b>{#if what && p.by}<em class="ellipsis">{p.by}</em>{/if}</span>{/if}
            </div>
          {/each}
        </div>
      {:else}
        <EmptyState icon={Images} title={t(`gallery.none.${theme}`)} />
      {/each}
    </div>
    {#if !data.galleryPost}<p class="note fs-sub faint">{t('gallery.note')}</p>{/if}
  {/if}
</Pane>
<input type="file" accept="image/*" multiple hidden bind:this={picker} onchange={picked} />

<style>
  .head { display: flex; align-items: center; justify-content: space-between; min-height: var(--ctl-s); padding: 0 var(--s-1); }
  .head.photos { margin-top: var(--s-6); }
  .more { position: relative; display: inline-flex; align-items: center; margin-right: -6px; color: var(--text-3); font: 450 var(--fs-body)/1.2 var(--font-text); }
  .more::after { content: ''; position: absolute; inset: -12px -4px; } /* 44 to the finger */
  .more:active { opacity: 0.5; transform: none; }

  /* albums: covers out to the right edge, the third one peeks in to say "swipe" */
  .shelf { gap: var(--s-2); margin: var(--s-2) calc(-1 * var(--gutter)) 0; padding: 0 var(--gutter); scroll-padding: 0 var(--gutter); }
  .alb { position: relative; flex: none; width: 150px; height: 96px; border-radius: var(--r-m); overflow: hidden; scroll-snap-align: start; text-align: left; }
  .alb:active { transform: none; opacity: 0.8; }
  .all { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .all .alb { width: auto; height: auto; aspect-ratio: 25 / 16; }
  .alb img, .ph img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }

  .themes { margin-top: var(--s-3); }
  .themes :global(.sgm button) { padding: 0; } /* five words across a phone */
  @media (max-width: 350px) { .themes :global(.sgm button) { font-size: var(--fs-cap); letter-spacing: -0.015em; } }

  /* the feed: a row's photos share its height; each takes width by its own shape (flex-grow = --ar) */
  .feed { display: flex; flex-direction: column; gap: 6px; margin-top: var(--s-4); min-height: 50vh; }
  .rowp { display: flex; align-items: flex-start; gap: 6px; content-visibility: auto; contain-intrinsic-size: auto 180px; }
  .ph { position: relative; flex: var(--ar) 1 0; min-width: 0; aspect-ratio: var(--ar); border-radius: var(--r-m); overflow: hidden; cursor: pointer;
    -webkit-tap-highlight-color: transparent; }
  .ph img { opacity: 0; transition: opacity 260ms ease-out; }
  .ph img:global(.in) { opacity: 1; }
  .ph:active img { opacity: 0.72; transition-duration: 0ms; }
  .ph:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  /* mine still uploading: the phone's own copy, dimmed, not to be opened yet */
  .wait { animation: g-wait 1.1s ease-in-out infinite; }
  @keyframes g-wait { 50% { opacity: 0.5; } }
  /* the lower shade a caption sits on, and a hairline that holds a pale photo's edge */
  .ph::after, .alb::after { content: ''; position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
    background: linear-gradient(transparent 52%, rgba(4, 6, 16, 0.3) 76%, rgba(4, 6, 16, 0.66)); box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.1); }
  .cap { position: absolute; z-index: 1; left: 0; right: 0; bottom: 0; padding: 0 var(--s-3) 10px; display: flex; flex-direction: column; gap: 2px; color: white; }
  .cap b { font: 600 var(--fs-sub)/1.2 var(--font-text); letter-spacing: -0.008em; }
  .cap em { font: 500 var(--fs-micro)/1.2 var(--font-text); font-style: normal; color: rgba(255, 255, 255, 0.74); }
  .note { margin-top: var(--s-4); padding: 0 var(--s-4); text-align: center; }
  @media (prefers-reduced-motion: reduce) { .ph img { transition: none; } .wait { animation: none; } }
</style>
