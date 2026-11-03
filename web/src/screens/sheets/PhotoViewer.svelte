<script lang="ts">
  // An album full screen (SPEC §4.9): the photos side by side, a swipe goes to the next (the browser's own scroll
  // snapping), "3 / 12" in the capsule. Telegram's Back or the app's one × (CloseX) leaves; mine, or any for the club's
  // Head+, can go. Who added it under the photo; another's can be reported: gone for me at once, the admin decides.
  // Pinch or a double tap zooms (owner, Nov 3: a person's photo opens here too, alone).
  import Images from '@lucide/svelte/icons/images';
  import { onMount } from 'svelte';
  import type { AlbumPhoto } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { glass } from '../../ui/glass';
  import CloseX from '../../ui/CloseX.svelte';

  let { overlay, photos, start = 0, onremove, ongone }: {
    overlay: Overlay; photos: AlbumPhoto[]; start?: number; onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>; ongone?: (p: AlbumPhoto) => void;
  } = $props();

  let list = $state<AlbumPhoto[]>([]);
  let at = $state(0);
  let root: HTMLDivElement;
  let strip: HTMLDivElement;
  let gone = false;

  onMount(() => {
    list = photos; at = start;
    requestAnimationFrame(() => { strip.scrollLeft = start * strip.clientWidth; });
    root.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease-out' });
    haptic.soft();
    return hideChrome();
  });
  function leave() {
    if (gone) return;
    gone = true;
    const a = root.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
  $effect(() => { overlay.title = list.length > 1 ? `${at + 1} / ${list.length}` : ''; overlay.icon = Images; }); // the capsule's title

  // zoom: the photo on show scales and pans by transform; the strip holds still while it's zoomed in
  let z = $state(1), x = $state(0), y = $state(0), held = $state(false);
  const pts = new Map<number, { x: number; y: number }>();
  let pinch: { d: number; z: number } | null = null, pan: { x: number; y: number; px: number; py: number } | null = null, lastTap = 0;
  const shown = () => strip.children[at]?.querySelector('img') as HTMLImageElement | null;
  const dist = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
  // the photo's edges never come inside the screen
  function clamp() {
    const im = shown();
    if (!im || z <= 1) { z = 1; x = 0; y = 0; return; }
    const mx = Math.max(0, (im.offsetWidth * z - strip.clientWidth) / 2), my = Math.max(0, (im.offsetHeight * z - strip.clientHeight) / 2);
    x = Math.max(-mx, Math.min(mx, x));
    y = Math.max(-my, Math.min(my, y));
  }
  function down(e: PointerEvent) {
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2) { pinch = { d: dist(), z }; pan = null; held = true; }
    else if (z > 1) { pan = { x, y, px: e.clientX, py: e.clientY }; held = true; }
  }
  function move(e: PointerEvent) {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pts.size === 2) { z = Math.min(4, Math.max(1, (pinch.z * dist()) / pinch.d)); clamp(); }
    else if (pan) { x = pan.x + e.clientX - pan.px; y = pan.y + e.clientY - pan.py; clamp(); }
  }
  function up(e: PointerEvent) {
    if (!pts.delete(e.pointerId)) return;
    if (pts.size < 2) pinch = null;
    if (!pts.size) { pan = null; held = false; }
    if (e.type !== 'pointerup') return;
    // a double tap: in at the tapped point, or back out
    if (e.timeStamp - lastTap > 300) { lastTap = e.timeStamp; return; }
    lastTap = 0;
    if (z > 1) { z = 1; x = 0; y = 0; return; }
    z = 2.5; x = (strip.clientWidth / 2 - e.clientX) * 1.5; y = (strip.clientHeight / 2 - e.clientY) * 1.5; clamp();
  }
  $effect(() => { void at; z = 1; x = 0; y = 0; }); // the next photo starts whole
  // two fingers are a pinch, never the strip's swipe (a passive listener can't say so: Svelte's ontouchmove is one)
  $effect(() => {
    const two = (e: TouchEvent) => { if (e.touches.length > 1 && e.cancelable) e.preventDefault(); };
    strip.addEventListener('touchmove', two, { passive: false });
    return () => strip.removeEventListener('touchmove', two);
  });

  // anything to say or do under the photo (an album's); a person's photo has the × alone
  const acts = $derived(!!list[at] && (!!list[at].by || !list[at].mine || (!!onremove && list[at].canDelete)));

  async function remove() {
    const p = list[at];
    if (!p || !onremove || !(await sheets.ask({ title: t('album.removeAsk'), ok: t('album.remove'), cancel: t('common.cancel'), danger: true }))) return;
    const left = await onremove(p);
    if (!left) return;
    haptic.soft();
    if (!left.length) { close(overlay.id); return; }
    list = left; at = Math.min(at, left.length - 1);
  }
  // the one report sheet; once sent the photo is hidden for me, so it leaves the viewer and the album
  function report() {
    const p = list[at];
    if (!p) return;
    sheets.report('photo', p.id, '', () => {
      ongone?.(p);
      const left = list.filter((x) => x.id !== p.id);
      if (!left.length) { close(overlay.id); return; }
      list = left; at = Math.min(at, left.length - 1);
    });
  }
</script>

<div class="viewer" bind:this={root}>
  <div class="strip" class:zoomed={z > 1} role="presentation" bind:this={strip} onscroll={() => (at = Math.round(strip.scrollLeft / strip.clientWidth))}
    onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
    {#each list as p, i (p.id)}
      <div class="slide" class:bare={!acts}><img src={p.url} alt="" decoding="async" draggable="false" class:held
        style:background-color={p.color ?? 'transparent'} style:transform={i === at && z > 1 ? `translate(${x}px, ${y}px) scale(${z})` : null} /></div>
    {/each}
  </div>
  {#if acts}
    <div class="acts">
      {#if list[at]?.by}<p class="by">{list[at].by}</p>{/if}
      <div class="row">
        {#if list[at] && !list[at].mine}<button class="pill glass glass-pill" use:glass onclick={report}>{t('cm.report')}</button>{/if}
        {#if onremove && list[at]?.canDelete}<button class="pill glass glass-pill danger" use:glass onclick={remove}>{t('album.remove')}</button>{/if}
      </div>
    </div>
  {/if}
  <CloseX onclick={() => close(overlay.id)} />
</div>

<style>
  .viewer { position: absolute; inset: 0; z-index: var(--z-sheet); background: #000; color: #fff; }
  .strip { position: absolute; inset: 0; display: flex; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; overscroll-behavior: contain; scrollbar-width: none;
    touch-action: pan-x; }
  .strip::-webkit-scrollbar { display: none; }
  /* zoomed in: one finger pans the photo (ours), the strip holds still */
  .strip.zoomed { overflow-x: hidden; touch-action: none; }
  .slide { flex: none; width: 100%; height: 100%; scroll-snap-align: center; scroll-snap-stop: always; display: flex; align-items: center; justify-content: center;
    padding: calc(var(--top) + 8px) 0 calc(var(--close-room) + 64px); }
  .slide.bare { padding-bottom: var(--close-room); }
  .slide img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; user-select: none; -webkit-user-select: none;
    transition: transform 220ms var(--ease); }
  .slide img.held { transition: none; } /* under the fingers: no lag */
  .acts { position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 16px var(--close-room);
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.5)); pointer-events: none; }
  .acts > * { pointer-events: auto; }
  .row { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; }
  .row:empty { display: none; }
  .by { font: 600 13px/1.2 var(--font-text); color: rgba(255, 255, 255, 0.75); text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6); }
  .pill { position: relative; height: 44px; padding: 0 24px; border-radius: var(--r-full); color: #fff; font: 650 15px/1 var(--font-text); background-color: rgba(255, 255, 255, 0.12); }
  .pill:active { transform: scale(0.96); }
  .danger { color: #FF8A80; background-color: rgba(255, 69, 58, 0.16); }
</style>
