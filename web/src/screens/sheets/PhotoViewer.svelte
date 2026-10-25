<script lang="ts">
  // An album full screen (SPEC §4.9): the photos side by side, a swipe goes to the next (the browser's own scroll
  // snapping), "3 / 12" in the capsule. Telegram's Back or Close leaves; mine, or any for the club's Head+, can go.
  // Who added it under the photo; another's can be reported: gone for me at once, the admin decides.
  import Images from '@lucide/svelte/icons/images';
  import X from '@lucide/svelte/icons/x';
  import { onMount } from 'svelte';
  import type { AlbumPhoto } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { glass } from '../../ui/glass';

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
  $effect(() => { overlay.title = list.length ? `${at + 1} / ${list.length}` : ''; overlay.icon = Images; }); // the capsule's title

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
  <div class="strip" bind:this={strip} onscroll={() => (at = Math.round(strip.scrollLeft / strip.clientWidth))}>
    {#each list as p (p.id)}
      <div class="slide"><img src={p.url} alt="" decoding="async" style="background-color:{p.color ?? 'transparent'}" /></div>
    {/each}
  </div>
  <div class="acts">
    {#if list[at]?.by}<p class="by">{list[at].by}</p>{/if}
    <div class="row">
    {#if list[at] && !list[at].mine}<button class="pill glass glass-pill" use:glass onclick={report}>{t('cm.report')}</button>{/if}
    {#if onremove && list[at]?.canDelete}<button class="pill glass glass-pill danger" use:glass onclick={remove}>{t('album.remove')}</button>{/if}
    <button class="pill x glass glass-pill" use:glass onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={20} strokeWidth={2.4} /></button>
    </div>
  </div>
</div>

<style>
  .viewer { position: absolute; inset: 0; z-index: var(--z-sheet); background: #000; color: #fff; }
  .strip { position: absolute; inset: 0; display: flex; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; overscroll-behavior: contain; scrollbar-width: none; }
  .strip::-webkit-scrollbar { display: none; }
  .slide { flex: none; width: 100%; height: 100%; scroll-snap-align: center; scroll-snap-stop: always; display: flex; align-items: center; justify-content: center;
    padding: calc(var(--top) + 8px) 0 calc(var(--safe-bottom) + 108px); }
  .slide img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }
  .acts { position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 16px calc(var(--safe-bottom) + 16px);
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.5)); }
  .row { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; }
  .by { font: 600 13px/1.2 var(--font-text); color: rgba(255, 255, 255, 0.75); text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6); }
  .pill { position: relative; height: 44px; padding: 0 24px; border-radius: var(--r-full); color: #fff; font: 650 15px/1 var(--font-text); background-color: rgba(255, 255, 255, 0.12); }
  .pill:active { transform: scale(0.96); }
  /* a round cross, not a worded pill (owner, Oct 25) */
  .pill.x { width: 44px; padding: 0; display: grid; place-items: center; }
  .danger { color: #FF8A80; background-color: rgba(255, 69, 58, 0.16); }
</style>
