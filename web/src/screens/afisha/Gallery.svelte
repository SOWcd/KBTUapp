<script lang="ts">
  // The Gallery, as the phone's Photos: nothing to choose, one "+". The events' albums as a strip of covers (a tap
  // opens the event with its album over it), then every photo as square tiles edge to edge, sorted by where it was
  // taken: main building, building 2, dorm, off campus, then the ones that say no place (lib/place.ts; the phone names
  // the place from the photo's own EXIF as it is added, no one picks anything). A tap opens the viewer, which says
  // whose it is and of which event. The "+" (GALLERY) opens the phone's picker; my photos land in the grid at once,
  // marked while they upload.
  import { calm } from '../../ui/fold';
  import Images from '@lucide/svelte/icons/images';
  import Plus from '@lucide/svelte/icons/plus';
  import RotateCw from '@lucide/svelte/icons/rotate-cw';
  import X from '@lucide/svelte/icons/x';
  import { onMount, tick } from 'svelte';
  import type { AlbumPhoto, GalleryAlbum } from '../../lib/api';
  import { data, deleteGallery, dropGallery, galleryGone, loadGallery, postGallery, retryGallery } from '../../lib/state/data.svelte';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { bySite } from '../../lib/place';
  import { focusPos } from '../../lib/photo';
  import { dayMonthShort } from '../../lib/time';
  import Pane from '../../ui/Pane.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay }: { overlay: Overlay } = $props();

  const sites = $derived(bySite(data.gallery));
  const shown = $derived(sites.flatMap((s) => s.photos)); // as drawn: the viewer swipes in this order
  const named = $derived(sites.some((s) => s.key !== 'none')); // no place anywhere: one grid, no headers
  // the whole feed as it opens, so the viewer swipes across all of it
  onMount(() => void loadGallery(true));
  // no large title here: the capsule says the name from the start (Pane hushes it as it mounts, after this runs once)
  $effect(() => { if (overlay.quiet) overlay.quiet = false; });

  // the photo's own tile: brought into view first, so the viewer closes into a place you can see
  let feed = $state<HTMLDivElement>();
  function cell(p: AlbumPhoto): Element | null {
    const el = feed?.querySelector(`[data-id="${p.id}"]`);
    const r = el?.getBoundingClientRect();
    if (r && (r.top < 100 || r.bottom > innerHeight - 40)) el!.scrollIntoView({ block: 'center' });
    return el ?? null;
  }
  const remove = async (p: AlbumPhoto) => ((await deleteGallery(p)) ? shown : null);
  const open = (p: AlbumPhoto) => { if (!p.pending && !p.failed) sheets.photos(shown, shown.indexOf(p), data.galleryPost ? remove : undefined, galleryGone, cell); };
  function fade(img: HTMLImageElement) {
    const on = () => img.classList.add('in');
    if (img.complete && img.naturalWidth) on(); else img.addEventListener('load', on, { once: true });
  }

  let picker = $state<HTMLInputElement>();
  function picked(e: Event) {
    const el = e.currentTarget as HTMLInputElement, files = [...(el.files ?? [])];
    el.value = '';
    if (files.length) void postGallery(files);
  }
  // my photos started: to where the newest landed (its place's own grid)
  let posted = data.galleryPosted;
  $effect(() => {
    if (data.galleryPosted === posted) return;
    posted = data.galleryPosted;
    void tick().then(() => feed?.querySelector('.mine.wait')?.scrollIntoView({ block: 'center', behavior: calm() ? 'auto' : 'smooth' }));
  });

  // an album's cover that didn't load: its newest photo here instead, never a blank card
  let broken = $state<Record<number, boolean>>({});
  const cover = (a: GalleryAlbum) => (broken[a.id] ? data.gallery.find((p) => p.event?.id === a.id && !p.pending)?.thumb : a.cover.thumb);
</script>

<Pane {overlay} icon={Images} title={t('gallery.title')} bare>
  <div class="page">
    {#if data.galleryAlbums.length}
      <h2 class="fs-t3">{t('gallery.albums')}</h2>
      <div class="shelf hscroll">
        {#each data.galleryAlbums as a (a.id)}
          {@const src = cover(a)}
          <button class="alb" style:background-color={a.cover.color ?? 'var(--surface-2)'} onclick={() => sheets.event(a.id, null, true)}>
            {#if src}<img {src} alt="" loading="lazy" decoding="async" draggable="false" style:object-position={broken[a.id] ? null : focusPos(a.cover)} onerror={() => (broken[a.id] = true)} />{/if}
            <span class="cap"><b>{a.title}</b><em class="num">{a.at ? dayMonthShort(a.at) + ' · ' : ''}{tn('gallery.photos', a.n)}</em></span>
          </button>
        {/each}
      </div>
    {/if}

    <div class="feed" bind:this={feed}>
      {#each sites as site (site.key)}
        {#if named}<h2 class="fs-t3">{t(`gallery.place.${site.key}`)}</h2>{/if}
        <!-- div[role=button], not button: Pane's swipe from the left edge starts anywhere but on a button -->
        <div class="grid">
          {#each site.photos as p (p.key ?? p.id)}
            <div class="c" class:wait={p.pending} class:mine={p.key != null} role="button" tabindex="0" aria-label={t('fc.photo')} aria-busy={p.pending} data-id={p.id}
              style:background-color={p.color ?? 'var(--surface-2)'} onclick={() => open(p)} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(p); } }}>
              <img src={p.thumb} alt="" loading="lazy" decoding="async" draggable="false" use:fade />
              {#if p.failed}
                <span class="again">
                  <IconButton icon={RotateCw} label={t('common.retry')} kind="glass" size="s" onclick={(e) => { e.stopPropagation(); void retryGallery(p); }} />
                  <IconButton icon={X} label={t('album.remove')} kind="glass" size="s" onclick={(e) => { e.stopPropagation(); dropGallery(p); }} />
                </span>
              {/if}
            </div>
          {/each}
        </div>
      {:else}
        {#if data.galleryState === 'new'}
          <div class="grid" aria-busy="true" aria-hidden="true">{#each { length: 9 } as _, i (i)}<div class="c ghost"></div>{/each}</div>
        {:else if data.galleryState === 'failed'}
          <EmptyState onretry={() => loadGallery(true)} />
        {:else}
          <EmptyState icon={Images} title={t('gallery.none')} text={t(data.galleryPost ? 'gallery.first' : 'gallery.note')} />
        {/if}
      {/each}
    </div>
    {#if data.galleryPost}
      <div class="plus"><IconButton icon={Plus} label={t('album.addMine')} kind="glass" size="l" onclick={() => picker?.click()} /></div>
    {:else if shown.length}
      <p class="note fs-sub faint">{t('gallery.note')}</p>
    {/if}
  </div>
</Pane>
<input type="file" accept="image/*" multiple hidden bind:this={picker} onchange={picked} />

<style>
  /* as tall as the page at least, so the "+" rests at the bottom over an empty Gallery too (the pane's own tail under it) */
  .page { display: flex; flex-direction: column; min-height: calc(100% - var(--safe-bottom) - 40px); }
  h2 { margin: var(--s-5) var(--s-1) var(--s-3); }
  h2:first-child { margin-top: 0; }
  .shelf + .feed > h2:first-child, .shelf + .feed > .grid:first-child { margin-top: var(--s-5); }

  /* albums: covers out to the right edge, one and a half in view to say "swipe" */
  .shelf { gap: var(--s-2); margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter); scroll-padding: 0 var(--gutter); }
  .alb { position: relative; flex: none; width: 220px; height: 140px; border-radius: var(--r-l); overflow: hidden; scroll-snap-align: start; text-align: left;
    transition: transform var(--t-fast) var(--ease); }
  .alb:active { transform: scale(0.98); }
  .alb img, .c img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
  /* the low shade the caption sits on, and a hairline that holds a pale cover's edge */
  .alb::after { content: ''; position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
    background: linear-gradient(to top, rgba(4, 6, 16, 0.58), rgba(4, 6, 16, 0.26) 36px, transparent 72px); box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.1); }
  .cap { position: absolute; z-index: 1; left: 0; right: 0; bottom: 0; padding: 0 14px 12px; display: flex; flex-direction: column; gap: 3px; color: white; }
  .cap b { font: 600 var(--fs-body)/1.2 var(--font-text); letter-spacing: -0.008em; overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 1; line-clamp: 1; overflow-wrap: anywhere; }
  .cap em { font: 500 var(--fs-cap)/1.2 var(--font-text); font-style: normal; color: rgba(255, 255, 255, 0.78); }

  /* the photos: squares edge to edge, out of the page's gutters, as the phone's grid (AlbumGrid's) */
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; margin: 0 calc(-1 * var(--gutter)); }
  @media (min-width: 600px) { .grid { grid-template-columns: repeat(4, 1fr); } }
  .c { position: relative; aspect-ratio: 1; overflow: hidden; cursor: pointer; -webkit-tap-highlight-color: transparent;
    content-visibility: auto; contain-intrinsic-size: auto 125px; }
  .c img { opacity: 0; transition: opacity 260ms ease-out; }
  .c img:global(.in) { opacity: 1; }
  .c:active img { opacity: 0.72; transition-duration: 0ms; }
  .c:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

  /* mine: it arrives (once), and while it uploads a ring turns in its corner, the photo itself at full strength */
  .mine.wait { animation: g-land 320ms var(--ease-spring) backwards; }
  @keyframes g-land { from { opacity: 0; transform: scale(0.86); } }
  .wait::before { content: ''; position: absolute; z-index: 2; top: 8px; right: 8px; width: 16px; height: 16px; border-radius: var(--r-full);
    border: 2px solid rgba(255, 255, 255, 0.36); border-top-color: white; filter: drop-shadow(0 0 3px rgba(4, 6, 16, 0.5)); animation: g-turn 0.9s linear infinite; }
  @keyframes g-turn { to { transform: rotate(360deg); } }
  .again { position: absolute; z-index: 2; inset: 0; display: flex; align-items: center; justify-content: center; gap: var(--s-2); background: rgba(4, 6, 16, 0.42); }
  /* not here yet: the grid's shape, breathing slowly */
  .ghost { background: var(--surface-2); cursor: default; animation: g-wait 1.6s ease-in-out infinite; }
  @keyframes g-wait { 50% { opacity: 0.55; } }

  /* the one control: held over the grid at the thumb's corner; at the page's end it rests under the last row */
  .plus { position: sticky; bottom: calc(var(--safe-bottom) + 24px); z-index: var(--z-sticky); align-self: flex-end; margin: auto 0 -16px; padding-top: var(--s-3); }
  .plus :global(.btn) { color: var(--accent-text); box-shadow: var(--glass-shadow); }
  .note { margin-top: var(--s-4); padding: 0 var(--s-4); text-align: center; }
  @media (prefers-reduced-motion: reduce) { .alb, .c img { transition: none; } .mine.wait, .wait::before, .ghost { animation: none; } }
</style>
