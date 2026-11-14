<script lang="ts">
  // The Gallery (owner's pick, Nov 11): the capsule names it, no large title. Two shelves, each with a clear end:
  // "Albums … All ›", the events' albums as dated cover cards in a strip (one and a half in view; a tap opens the event
  // with its album over it), and "Photos … Add", the one tinted control (GALLERY: pick, then GalleryAdd). Under it the
  // themes, which stay under the capsule on glass as the feed scrolls, with a round "+" at their end once the Add has
  // scrolled away. The feed is told by time and people (round 2): "Today", "Yesterday", "This week", then months
  // (lib/gallery), justified rows inside each, the newest photo large; a tile says whose it is, an event's its event
  // first. My own posts land on top under All, marked while they upload. `albums`: every album alone, two a row.
  import { calm } from '../../ui/fold';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Images from '@lucide/svelte/icons/images';
  import Plus from '@lucide/svelte/icons/plus';
  import RotateCw from '@lucide/svelte/icons/rotate-cw';
  import X from '@lucide/svelte/icons/x';
  import { onMount } from 'svelte';
  import type { AlbumPhoto, GalleryAlbum, GalleryTopic } from '../../lib/api';
  import { data, deleteGallery, dropGallery, galleryGone, loadGallery, loadGalleryTheme, retryGallery } from '../../lib/state/data.svelte';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { groups } from '../../lib/gallery';
  import { focusPos } from '../../lib/photo';
  import { dayMonthShort } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Segmented from '../../ui/Segmented.svelte';

  let { overlay, albums = false }: { overlay: Overlay; albums?: boolean } = $props();

  // posting is for me: every theme; else the albums' photos alone, so no theme to pick
  const THEMES = ['all', 'events', 'campus', 'study', 'life'] as const; // "other" photos: under All alone
  type Theme = (typeof THEMES)[number];
  let theme = $state<Theme>('all');
  const shown = $derived(theme === 'all' ? data.gallery : data.gallery.filter((p) => (theme === 'events' ? !!p.event : p.topic === theme)));
  const days = $derived(groups(shown));

  let asked = $state<Partial<Record<Theme, 'wait' | 'ok' | 'failed'>>>({}); // each theme's own first page
  async function ask(v: Theme) {
    if (v === 'all') return void loadGallery(true);
    asked[v] = 'wait';
    asked[v] = (await loadGalleryTheme(v)) ? 'ok' : 'failed';
  }
  let feed = $state<HTMLDivElement>();
  function pick(v: Theme) {
    haptic.select();
    if (!calm()) feed?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 140, easing: 'ease-out' });
    if (v !== 'all' && asked[v] !== 'ok' && asked[v] !== 'wait') void ask(v);
  }
  // what the feed is, when it has no photo to show
  const phase = $derived(shown.length ? 'photos' : theme === 'all' ? (data.galleryState === 'ready' ? 'empty' : data.galleryState === 'failed' ? 'failed' : 'wait')
    : asked[theme] === 'failed' || data.galleryState === 'failed' ? 'failed' : asked[theme] === 'wait' || data.galleryState === 'new' ? 'wait' : 'empty');
  // the whole feed as it opens, so the viewer swipes across all of it
  onMount(() => { if (!albums) void loadGallery(true); });
  // no large title here: the capsule says the name from the start (Pane hushes it as it mounts, after this runs once)
  $effect(() => { if (overlay.quiet) overlay.quiet = false; });

  // the photo's own tile: brought into view first, so the viewer closes into a place you can see
  function cell(p: AlbumPhoto): Element | null {
    const el = feed?.querySelector(`[data-id="${p.id}"]`);
    const r = el?.getBoundingClientRect();
    if (r && (r.top < 140 || r.bottom > innerHeight - 40)) el!.scrollIntoView({ block: 'center' });
    return el ?? null;
  }
  const remove = async (p: AlbumPhoto) => ((await deleteGallery(p)) ? shown : null);
  const view = (i: number) => sheets.photos(shown, i, data.galleryPost ? remove : undefined, galleryGone, cell);
  const open = (p: AlbumPhoto, i: number) => { if (!p.pending && !p.failed) view(i); };
  const key = (e: KeyboardEvent, go: () => void) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
  function fade(img: HTMLImageElement) {
    const on = () => img.classList.add('in');
    if (img.complete && img.naturalWidth) on(); else img.addEventListener('load', on, { once: true });
  }

  // Add: the phone's picker, then the sheet; under a theme of photos, that theme chosen already
  let picker = $state<HTMLInputElement>();
  let into: GalleryTopic | undefined;
  function add(topic?: Theme) {
    into = topic === 'campus' || topic === 'study' || topic === 'life' ? topic : undefined;
    picker?.click();
  }
  function picked(e: Event) {
    const el = e.currentTarget as HTMLInputElement, files = [...(el.files ?? [])].slice(0, 10); // at once, as the store takes
    el.value = '';
    if (files.length) sheets.galleryAdd(files, into);
  }

  // the "Photos" head gone under the capsule: the themes are on glass now and carry the Add
  let head = $state<HTMLDivElement>();
  let stuck = $state(false);
  $effect(() => {
    if (!head) return;
    const io = new IntersectionObserver(([e]) => { stuck = !e.isIntersecting && e.boundingClientRect.top < 200; }, { rootMargin: '-90px 0px 0px 0px' });
    io.observe(head);
    return () => io.disconnect();
  });
  // my post started: All, and the feed's top, where it lands
  let posted = data.galleryPosted;
  $effect(() => {
    if (data.galleryPosted === posted) return;
    posted = data.galleryPosted;
    theme = 'all';
    head?.scrollIntoView({ block: 'start', behavior: calm() ? 'auto' : 'smooth' });
  });

  // an album's cover that didn't load: its newest photo here instead, never a blank card
  let broken = $state<Record<number, boolean>>({});
  const cover = (a: GalleryAlbum) => (broken[a.id] ? data.gallery.find((p) => p.event?.id === a.id && !p.pending)?.thumb : a.cover.thumb);
  const WAIT = [[1.5], [0.8, 1.5], [1.6, 0.75]]; // the rows a cold open draws until the first page is known
</script>

{#snippet card(a: GalleryAlbum)}
  {@const src = cover(a)}
  <button class="alb" style:background-color={a.cover.color ?? 'var(--surface-2)'} onclick={() => sheets.event(a.id, null, true)}>
    {#if src}<img {src} alt="" loading="lazy" decoding="async" draggable="false" style:object-position={broken[a.id] ? null : focusPos(a.cover)} onerror={() => (broken[a.id] = true)} />{/if}
    <span class="cap"><b>{a.title}</b><em class="num">{a.at ? dayMonthShort(a.at) + ' · ' : ''}{tn('gallery.photos', a.n)}</em></span>
  </button>
{/snippet}

<Pane {overlay} icon={Images} title={t(albums ? 'gallery.albums' : 'gallery.title')} bare>
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

    <div class="head photos" bind:this={head}>
      <h2 class="fs-t3">{t('album.title')}</h2>
      {#if data.galleryPost}<Button kind="tinted" size="s" onclick={() => add(theme)}>{#snippet icon()}<Plus size={16} strokeWidth={2.4} />{/snippet}{t('album.add')}</Button>{/if}
    </div>
    {#if data.galleryPost}
      <div class="themes" class:stuck>
        <div class="bar"><Segmented items={THEMES.map((k) => ({ value: k, label: t(`gallery.t.${k}`) }))} bind:value={theme} label={t('gallery.topic')} onchange={pick} /></div>
        <span class="plus" inert={!stuck}><IconButton icon={Plus} label={t('album.addMine')} kind="glass" size="s" onclick={() => add(theme)} /></span>
      </div>
    {/if}

    <!-- div[role=button], not button: Pane's swipe from the left edge starts anywhere but on a button -->
    <div class="feed" bind:this={feed}>
      {#each days as day, n (day.key)}
        {#if day.label}<h3 class="day" class:first={n === 0}>{day.label}</h3>{/if}
        <div class="set">
          {#each day.rows as row (row.tiles[0].p.key ?? row.tiles[0].p.id)}
            <div class="rowp" class:lead={row.lead} class:three={row.tiles.length === 3}>
              {#each row.tiles as { p, i, ar } (p.key ?? p.id)}
                {@const what = p.event?.title}
                <div class="ph" class:wait={p.pending} class:mine={p.key != null} class:plain={!what && !p.by} class:two={!!what && !!p.by} role="button" tabindex="0" data-id={p.id}
                  style:--ar={ar} style:background-color={p.color ?? 'var(--surface-2)'} style:background-image={p.blur ? `url("${p.blur}")` : null}
                  aria-busy={p.pending} onclick={() => open(p, i)} onkeydown={(e) => key(e, () => open(p, i))}>
                  <img src={p.thumb} alt="" loading="lazy" decoding="async" draggable="false" use:fade />
                  {#if p.failed}
                    <span class="again">
                      <IconButton icon={RotateCw} label={t('common.retry')} kind="glass" size="s" onclick={(e) => { e.stopPropagation(); void retryGallery(p); }} />
                      <IconButton icon={X} label={t('album.remove')} kind="glass" size="s" onclick={(e) => { e.stopPropagation(); dropGallery(p); }} />
                    </span>
                  {:else if what || p.by}
                    <span class="cap"><b class="ellipsis">{what ?? p.by}</b>{#if what && p.by}<em class="ellipsis">{p.by}</em>{/if}</span>
                  {/if}
                </div>
              {/each}
            </div>
          {/each}
        </div>
      {:else}
        {#if phase === "wait"}
          <div class="set" aria-busy="true" aria-hidden="true">
            {#each WAIT as row, r (r)}<div class="rowp" class:lead={r === 0}>{#each row as ar, c (c)}<div class="ph ghost" style:--ar={ar}></div>{/each}</div>{/each}
          </div>
        {:else if phase === "failed"}
          <EmptyState onretry={() => ask(theme)} />
        {:else if data.galleryPost && theme !== 'events'}
          <EmptyState icon={Images} title={t(`gallery.none.${theme}`)} text={t('gallery.first')} action={{ label: t('album.addMine'), onclick: () => add(theme) }} />
        {:else}
          <EmptyState icon={Images} title={t(`gallery.none.${theme}`)} text={t('gallery.note')} />
        {/if}
      {/each}
    </div>
    {#if !data.galleryPost && shown.length}<p class="note fs-sub faint">{t('gallery.note')}</p>{/if}
  {/if}
</Pane>
<input type="file" accept="image/*" multiple hidden bind:this={picker} onchange={picked} />

<style>
  .head { display: flex; align-items: center; justify-content: space-between; min-height: var(--ctl-s); padding: 0 var(--s-1); }
  .head.photos { margin-top: var(--s-5); scroll-margin-top: var(--page-top); }
  .more { position: relative; display: inline-flex; align-items: center; margin-right: -6px; color: var(--text-3); font: 450 var(--fs-body)/1.2 var(--font-text); }
  .more::after { content: ''; position: absolute; inset: -12px -4px; } /* 44 to the finger */
  .more:active { opacity: 0.5; transform: none; }

  /* albums: covers out to the right edge, one and a half in view to say "swipe" */
  .shelf { gap: var(--s-2); margin: var(--s-2) calc(-1 * var(--gutter)) 0; padding: 0 var(--gutter); scroll-padding: 0 var(--gutter); }
  .alb { position: relative; flex: none; width: 220px; height: 140px; border-radius: var(--r-l); overflow: hidden; scroll-snap-align: start; text-align: left;
    transition: transform var(--t-fast) var(--ease); }
  .alb:active { transform: scale(0.98); }
  .all { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .all .alb { width: auto; height: auto; aspect-ratio: 5 / 4; border-radius: var(--r-m); }
  .alb img, .ph img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
  .alb .cap { padding: 0 14px 12px; gap: 3px; }
  .alb .cap b { font-size: var(--fs-body); overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 1; line-clamp: 1; overflow-wrap: anywhere; }
  .all .alb .cap { padding: 0 var(--s-3) 10px; }
  .all .alb .cap b { font-size: var(--fs-sub); -webkit-line-clamp: 2; line-clamp: 2; }
  .alb .cap em { font-size: var(--fs-cap); }

  /* the themes: in place under "Photos", then held under the capsule on glass while the feed runs under them */
  .themes { position: sticky; top: 0; /* from inside the pane's padding: right under the capsule */ z-index: var(--z-sticky); display: flex; align-items: center; margin-top: var(--s-3); }
  .bar { position: relative; flex: 1; min-width: 0; border-radius: var(--r-full); transition: background-color var(--t-base) var(--ease), box-shadow var(--t-base) var(--ease); }
  /* thick glass (the Menu's): a caption passing under it must not read through the words */
  .stuck .bar { background-color: var(--menu-bg); box-shadow: var(--glass-shadow); -webkit-backdrop-filter: blur(24px) saturate(190%); backdrop-filter: blur(24px) saturate(190%); }
  .themes :global(.sgm button) { padding: 0; } /* five words across a phone */
  .plus { flex: none; display: inline-flex; width: 0; opacity: 0; transform: scale(0.6); transition: width var(--t-base) var(--ease), opacity var(--t-base) var(--ease), transform var(--t-base) var(--ease), margin var(--t-base) var(--ease); }
  .stuck .plus { width: var(--ctl-s); margin-left: var(--s-2); opacity: 1; transform: none; }
  .plus :global(.btn) { color: var(--accent-text); }
  @media (max-width: 350px) { .themes :global(.sgm button) { font-size: var(--fs-cap); letter-spacing: -0.015em; } .stuck :global(.sgm button) { font-size: var(--fs-micro); letter-spacing: -0.03em; } }

  /* the feed: stretches of time; in each, a row's photos share its height and take width by their own shape (flex-grow = --ar) */
  .feed { margin-top: var(--s-4); min-height: 60vh; }
  .day { margin: var(--s-5) var(--s-1) var(--s-2); font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .day.first { margin-top: 0; }
  .set { display: flex; flex-direction: column; gap: var(--s-1); }
  .rowp { display: flex; align-items: flex-start; gap: var(--s-1); content-visibility: auto; contain-intrinsic-size: auto 180px; }
  .ph { position: relative; flex: var(--ar) 1 0; min-width: 0; aspect-ratio: var(--ar); border-radius: var(--r-m); overflow: hidden; cursor: pointer;
    background-size: cover; background-position: center; -webkit-tap-highlight-color: transparent; transition: transform var(--t-fast) var(--ease); }
  .ph:only-child { flex-grow: 1; } /* a grow under 1 would leave the row short */
  .lead .ph { border-radius: var(--r-l); }
  .ph:active { transform: scale(0.98); }
  .ph img { opacity: 0; transition: opacity 260ms ease-out; }
  .ph img:global(.in) { opacity: 1; }
  .ph:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  /* the low shade a caption sits on, as tall as the caption and no more, and a hairline that holds a pale photo's edge */
  .ph::after, .alb::after { content: ''; position: absolute; inset: 0; pointer-events: none; border-radius: inherit; --band: 52px;
    background: linear-gradient(to top, rgba(4, 6, 16, 0.58), rgba(4, 6, 16, 0.26) calc(var(--band) * 0.5), transparent var(--band)); box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.1); }
  .ph.two::after, .alb::after { --band: 72px; }
  .ph.plain::after, .ph.ghost::after { background: none; }
  .cap { position: absolute; z-index: 1; left: 0; right: 0; bottom: 0; padding: 0 var(--s-3) 10px; display: flex; flex-direction: column; gap: 2px; color: white; }
  .cap b { font: 600 var(--fs-sub)/1.2 var(--font-text); letter-spacing: -0.008em; }
  .cap em { font: 500 var(--fs-micro)/1.2 var(--font-text); font-style: normal; color: rgba(255, 255, 255, 0.78); }
  /* three across: room for one line */
  .three .cap { padding: 0 var(--s-2) var(--s-2); }
  .three .cap em { display: none; }
  .three .ph.two::after { --band: 52px; }
  @media (max-width: 350px) { .three .cap { display: none; } .three .ph::after { background: none; } }

  /* mine: it arrives (once), and while it uploads a ring turns in its corner, the photo itself at full strength */
  .mine.wait { animation: g-land 240ms var(--ease) backwards; }
  @keyframes g-land { from { opacity: 0; transform: scale(0.94); } }
  .wait::before { content: ''; position: absolute; z-index: 2; top: 10px; right: 10px; width: 18px; height: 18px; border-radius: var(--r-full);
    border: 2px solid rgba(255, 255, 255, 0.36); border-top-color: white; filter: drop-shadow(0 0 3px rgba(4, 6, 16, 0.5)); animation: g-turn 0.9s linear infinite; }
  @keyframes g-turn { to { transform: rotate(360deg); } }
  .again { position: absolute; z-index: 2; inset: 0; display: flex; align-items: center; justify-content: center; gap: var(--s-2); background: rgba(4, 6, 16, 0.42); }
  /* not here yet: the rows' shapes, breathing slowly */
  .ghost { background: var(--surface-2); cursor: default; animation: g-wait 1.6s ease-in-out infinite; }
  @keyframes g-wait { 50% { opacity: 0.55; } }
  .note { margin-top: var(--s-4); padding: 0 var(--s-4); text-align: center; }
  @media (prefers-reduced-motion: reduce) { .ph, .alb, .plus, .bar { transition: none; } .ph img { transition: none; } .mine.wait, .wait::before, .ghost { animation: none; } }
</style>
