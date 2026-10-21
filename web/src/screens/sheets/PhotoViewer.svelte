<script lang="ts">
  // An album full screen (SPEC §4.9): the photos side by side, a swipe goes to the next (the browser's own scroll
  // snapping), "3 / 12" in the capsule. Telegram's Back or Close leaves; mine, or any for the club's Head+, can go.
  // Who added it under the photo; another's can be reported: gone for me at once, the admin decides.
  import Images from '@lucide/svelte/icons/images';
  import { onMount } from 'svelte';
  import { api, type AlbumPhoto, type ReportReason } from '../../lib/api';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { glass } from '../../ui/glass';

  let { overlay, photos, start = 0, onremove, ongone }: {
    overlay: Overlay; photos: AlbumPhoto[]; start?: number; onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>; ongone?: (p: AlbumPhoto) => void;
  } = $props();
  const REASONS: ReportReason[] = ['spam', 'insult', 'danger', 'other'];
  let reporting = $state(false);

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
  async function report(r: ReportReason) {
    const p = list[at];
    if (!p) return;
    try { await api.report('photo', p.id, r); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); return; }
    reporting = false; haptic.ok(); say(t('cm.reported'), 'raising_hands_3d_default'); ongone?.(p);
    const left = list.filter((x) => x.id !== p.id);
    if (!left.length) { close(overlay.id); return; }
    list = left; at = Math.min(at, left.length - 1);
  }
</script>

<div class="viewer" bind:this={root}>
  <div class="strip" bind:this={strip} onscroll={() => { at = Math.round(strip.scrollLeft / strip.clientWidth); reporting = false; }}>
    {#each list as p (p.id)}
      <div class="slide"><img src={p.url} alt="" decoding="async" style="background-color:{p.color ?? 'transparent'}" /></div>
    {/each}
  </div>
  <div class="acts">
    {#if list[at]?.by}<p class="by">{list[at].by}</p>{/if}
    {#if reporting}
      <div class="why">{#each REASONS as r (r)}<button class="pill glass glass-pill" use:glass onclick={() => report(r)}>{t(`rep.${r}`)}</button>{/each}</div>
    {/if}
    <div class="row">
    {#if list[at] && !list[at].mine && !reporting}<button class="pill glass glass-pill" use:glass onclick={() => (reporting = true)}>{t('cm.report')}</button>{/if}
    {#if onremove && list[at]?.canDelete}<button class="pill glass glass-pill danger" use:glass onclick={remove}>{t('album.remove')}</button>{/if}
    <button class="pill glass glass-pill" use:glass onclick={() => close(overlay.id)}>{t('common.close')}</button>
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
  .row, .why { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; }
  .why .pill { height: 38px; padding: 0 16px; font-size: 14px; }
  .by { font: 600 13px/1.2 var(--font-text); color: rgba(255, 255, 255, 0.75); text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6); }
  .pill { position: relative; height: 44px; padding: 0 24px; border-radius: var(--r-full); color: #fff; font: 650 15px/1 var(--font-text); background-color: rgba(255, 255, 255, 0.12); }
  .pill:active { transform: scale(0.96); }
  .danger { color: #FF8A80; background-color: rgba(255, 69, 58, 0.16); }
</style>
