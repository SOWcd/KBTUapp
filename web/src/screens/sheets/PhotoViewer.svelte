<script lang="ts">
  // An album full screen (SPEC §4.9), as the phone's Photos (owner, Nov 8): the photo grows out of the square it was
  // tapped in and shrinks back into the one it is on when it closes; a swipe goes to the next (the browser's own
  // scroll, its momentum and snapping), a pull down drags the photo away (it shrinks, the black fades; far or fast
  // enough it closes into its square, else springs back); pinch or a double tap zooms at the fingers, a zoomed photo
  // pans with a rubber edge. A tap hides and shows the chrome: "3 / 12" in the capsule, the filmstrip (it follows the
  // photo, a tap jumps), who added it and when, and ⋯: report (another's: gone for me at once, the admin decides) and
  // delete (mine, or any for the club's Head+). Telegram's Back or the app's one × (CloseX) leaves. A person's lone photo (owner, Nov 3)
  // opens here too: a tap closes it. Every move is transform and opacity (clip-path in the flight).
  import Images from '@lucide/svelte/icons/images';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Flag from '@lucide/svelte/icons/flag';
  import Trash from '@lucide/svelte/icons/trash-2';
  import { onMount, untrack } from 'svelte';
  import { menu } from '../../ui/menu';
  import { dayMonth, nowTs, parts } from '../../lib/time';
  import type { AlbumPhoto } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { data } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { glass } from '../../ui/glass';
  import CloseX from '../../ui/CloseX.svelte';

  let { overlay, photos, start = 0, onremove, ongone, from }: {
    overlay: Overlay; photos: AlbumPhoto[]; start?: number; onremove?: (p: AlbumPhoto) => Promise<AlbumPhoto[] | null>; ongone?: (p: AlbumPhoto) => void;
    from?: Element | ((p: AlbumPhoto) => Element | null | undefined);
  } = $props();

  // the viewer's own copy from the start (the first slide is in the DOM for the flight); remove and report change it
  let list = $state<AlbumPhoto[]>(untrack(() => photos));
  let at = $state(untrack(() => start));
  let chrome = $state(true);
  let root: HTMLDivElement, strip: HTMLDivElement, bd: HTMLDivElement, film: HTMLDivElement | undefined = $state();
  let gone = false;
  const calm = () => matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('lowfx');
  const thumbOf = (p: AlbumPhoto) => (typeof from === 'function' ? from(p) : from) ?? null;

  // the photo's box (its slide inside the padding) and the photo as it sits there, contained
  type Box = { l: number; t: number; w: number; h: number };
  const slideOf = (i = at) => strip.children[i] as HTMLElement | undefined;
  function boxOf(i = at): Box {
    const s = slideOf(i)!, r = s.getBoundingClientRect(), cs = getComputedStyle(s);
    const pl = parseFloat(cs.paddingLeft), pt = parseFloat(cs.paddingTop);
    return { l: r.left + pl, t: r.top + pt, w: r.width - pl - parseFloat(cs.paddingRight), h: r.height - pt - parseFloat(cs.paddingBottom) };
  }
  function fitOf(i = at, b = boxOf(i)) {
    const p = list[i], im = slideOf(i)?.querySelector('img');
    const iw = p?.w || im?.naturalWidth || b.w, ih = p?.h || im?.naturalHeight || b.h;
    const s = Math.min(b.w / iw, b.h / ih);
    return { w: iw * s, h: ih * s };
  }
  // the flight's end at the thumbnail: centred on it, scaled to cover it, clipped to its shape (FLIP)
  function toThumb(th: Element, b: Box, f: { w: number; h: number }): Keyframe {
    const r = th.getBoundingClientRect(), s = Math.max(r.width / f.w, r.height / f.h);
    const rad = getComputedStyle(th).borderTopLeftRadius, rr = rad.endsWith('%') ? (r.width * parseFloat(rad)) / 100 : parseFloat(rad) || 0;
    const tx = r.left + r.width / 2 - (b.l + b.w / 2), ty = r.top + r.height / 2 - (b.t + b.h / 2);
    return { transform: `translate(${tx}px, ${ty}px) scale(${s})`, clipPath: `inset(${(b.h - r.height / s) / 2}px ${(b.w - r.width / s) / 2}px round ${rr / s}px)` };
  }
  const whole = (b: Box, f: { w: number; h: number }): Keyframe => ({ transform: 'none', clipPath: `inset(${(b.h - f.h) / 2}px ${(b.w - f.w) / 2}px round 0px)` });
  const onScreen = (el: Element) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const hide = (el: Element | null, h: boolean) => { if (el instanceof HTMLElement) el.style.visibility = h ? 'hidden' : ''; };

  onMount(() => {
    const undo = hideChrome();
    strip.scrollLeft = start * strip.clientWidth; // now, so the flight starts from the right slide
    haptic.soft();
    const th = thumbOf(photos[start]);
    if (th && !calm() && onScreen(th)) {
      const pic = slideOf(start)!.firstElementChild as HTMLElement, b = boxOf(start), f = fitOf(start, b);
      hide(th, true);
      const ease = 'cubic-bezier(0.2, 0.85, 0.25, 1)';
      pic.animate([toThumb(th, b, f), whole(b, f)], { duration: 380, easing: ease }).onfinish = () => hide(th, false);
      bd.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, easing: 'ease-out' });
      for (const el of root.querySelectorAll('.chrome')) el.animate([{ opacity: 0 }, { opacity: 0 }, { opacity: 1 }], { duration: 420 });
    } else root.animate([{ opacity: 0 }, { opacity: 1 }], { duration: calm() ? 120 : 220, easing: 'ease-out' });
    return undo;
  });
  function leave() {
    if (gone) return;
    gone = true;
    const p = list[at], th = p && thumbOf(p), pic = slideOf()?.firstElementChild as HTMLElement | undefined;
    if (th && pic && !calm() && onScreen(th)) {
      const b = boxOf(), f = fitOf(at, b), now = getComputedStyle(pic).transform;
      hide(th, true);
      const a = pic.animate([{ transform: now === 'none' ? 'none' : now, clipPath: whole(b, f).clipPath }, toThumb(th, b, f)], { duration: 340, easing: 'cubic-bezier(0.3, 0.7, 0.2, 1)', fill: 'forwards' });
      bd.animate([{ opacity: getComputedStyle(bd).opacity }, { opacity: 0 }], { duration: 280, easing: 'ease-out', fill: 'forwards' });
      for (const el of root.querySelectorAll('.chrome')) el.animate([{ opacity: getComputedStyle(el).opacity }, { opacity: 0 }], { duration: 160, fill: 'forwards' });
      a.onfinish = () => { hide(th, false); removeOverlay(overlay.id); };
      return;
    }
    const a = root.animate([{ opacity: 1 }, { opacity: 0 }], { duration: calm() ? 120 : 200, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
  $effect(() => { overlay.title = list.length > 1 ? `${at + 1} / ${list.length}` : ''; overlay.icon = Images; }); // the capsule's title

  // the filmstrip follows the photo on show, its square in the middle
  $effect(() => {
    const el = film?.children[at] as HTMLElement | undefined;
    if (!film || !el) return;
    film.scrollTo({ left: el.offsetLeft + el.offsetWidth / 2 - film.clientWidth / 2, behavior: calm() || !film.dataset.ready ? 'instant' : 'smooth' });
    film.dataset.ready = '1';
  });
  const jump = (i: number) => { strip.scrollLeft = i * strip.clientWidth; haptic.select(); };

  // zoom: the photo on show scales and pans by transform; the strip holds still while it's zoomed in.
  // A pull down (not zoomed): dx, dy follow the finger
  let z = $state(1), x = $state(0), y = $state(0), held = $state(false), dx = $state(0), dy = $state(0);
  let drag: { x: number; y: number } | null = null, tapTimer: ReturnType<typeof setTimeout> | undefined, moved = false, past = false;
  let vy = 0, last = { y: 0, t: 0 };
  const pts = new Map<number, { x: number; y: number }>();
  let pinch: { d: number; z: number; qx: number; qy: number } | null = null, pan: { x: number; y: number; px: number; py: number } | null = null, lastTap = 0;
  const pair = () => [...pts.values()];
  const dist = () => { const [a, b] = pair(); return Math.hypot(a.x - b.x, a.y - b.y); };
  const mid = () => { const [a, b] = pair(); return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };
  // where the photo's edges may go at zoom z: never inside the screen (or centred on it when smaller)
  function range(z: number) {
    const b = boxOf(), f = fitOf(at, b), cx = b.l + b.w / 2, cy = b.t + b.h / 2, W = strip.clientWidth, H = strip.clientHeight;
    const lim = (c: number, half: number, S: number) => { const lo = S - c - half, hi = half - c; return lo > hi ? [(lo + hi) / 2, (lo + hi) / 2] : [lo, hi]; };
    return { x: lim(cx, (f.w * z) / 2, W), y: lim(cy, (f.h * z) / 2, H) };
  }
  // past an edge the photo still moves, a third as far (the rubber band); let go, it settles (clamp)
  const rub = (v: number, [lo, hi]: number[]) => (v < lo ? lo - (lo - v) / 3 : v > hi ? hi + (v - hi) / 3 : v);
  const fix = (v: number, [lo, hi]: number[]) => Math.max(lo, Math.min(hi, v));
  function clamp() {
    if (z <= 1) { z = 1; x = 0; y = 0; return; }
    if (z > 4) z = 4;
    const r = range(z);
    x = fix(x, r.x); y = fix(y, r.y);
  }
  function down(e: PointerEvent) {
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    moved = false; past = false;
    if (pts.size === 1 && z === 1) { drag = { x: e.clientX, y: e.clientY }; last = { y: e.clientY, t: e.timeStamp }; vy = 0; } else drag = null;
    if (pts.size === 2) {
      // the point under the fingers stays under them as they spread
      const b = boxOf(), m = mid();
      pinch = { d: dist(), z, qx: (m.x - b.l - b.w / 2 - x) / z, qy: (m.y - b.t - b.h / 2 - y) / z };
      pan = null; held = true; dx = 0; dy = 0;
    } else if (z > 1) { pan = { x, y, px: e.clientX, py: e.clientY }; held = true; }
  }
  function move(e: PointerEvent) {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pts.size === 2) {
      const raw = (pinch.z * dist()) / pinch.d;
      z = raw < 1 ? 1 - (1 - raw) / 2 : raw > 4 ? 4 + (raw - 4) / 3 : raw; // the rubber at both ends
      const b = boxOf(), m = mid();
      x = m.x - b.l - b.w / 2 - z * pinch.qx; y = m.y - b.t - b.h / 2 - z * pinch.qy;
      moved = true;
    } else if (drag && pts.size === 1) {
      const ddy = e.clientY - drag.y;
      if (dy > 0 || (ddy > 10 && ddy > Math.abs(e.clientX - drag.x))) {
        held = true; moved = true;
        dy = Math.max(0, ddy); dx = e.clientX - drag.x;
        vy = (e.clientY - last.y) / Math.max(1, e.timeStamp - last.t); last = { y: e.clientY, t: e.timeStamp };
        if (past !== dy > 100) { past = dy > 100; if (past) haptic.soft(); }
      }
    } else if (pan) {
      const r = range(z);
      x = rub(pan.x + e.clientX - pan.px, r.x); y = rub(pan.y + e.clientY - pan.py, r.y);
      moved = true;
    }
  }
  function up(e: PointerEvent) {
    if (!pts.delete(e.pointerId)) return;
    if (pts.size < 2 && pinch) { pinch = null; held = false; clamp(); }
    if (!pts.size) { pan = null; held = false; clamp(); }
    if (drag && dy > 0) {
      drag = null;
      // far enough, or flicked down: it closes into its square from where it is
      if (e.type === 'pointerup' && (dy > 100 || vy > 0.6)) { haptic.soft(); close(overlay.id, true); return; }
      dx = 0; dy = 0; return;
    }
    drag = null;
    if (e.type !== 'pointerup' || moved) return;
    clearTimeout(tapTimer);
    // a single tap (after the double-tap window): a person's lone photo leaves, an album's chrome hides or shows
    if (z === 1 && e.timeStamp - lastTap > 300) tapTimer = setTimeout(() => { if (list.length === 1 && !acts) close(overlay.id); else chrome = !chrome; }, 300);
    // a double tap: in at the tapped point, or back out
    if (e.timeStamp - lastTap > 300) { lastTap = e.timeStamp; return; }
    lastTap = 0;
    if (z > 1) { z = 1; x = 0; y = 0; return; }
    const b = boxOf();
    z = 2.5; x = (b.l + b.w / 2 - e.clientX) * 1.5; y = (b.t + b.h / 2 - e.clientY) * 1.5; clamp();
  }
  $effect(() => { void at; z = 1; x = 0; y = 0; }); // the next photo starts whole
  // two fingers are a pinch, never the strip's swipe (a passive listener can't say so: Svelte's ontouchmove is one)
  $effect(() => {
    const two = (e: TouchEvent) => { if (e.touches.length > 1 && e.cancelable) e.preventDefault(); };
    strip.addEventListener('touchmove', two, { passive: false });
    return () => strip.removeEventListener('touchmove', two);
  });

  const shrink = $derived(1 - Math.min(dy, 600) / 1500); // the pulled photo gets smaller as it goes
  const picMove = $derived(z !== 1 || x || y ? `translate(${x}px, ${y}px) scale(${z})` : dx || dy ? `translate(${dx}px, ${dy}px) scale(${shrink})` : null);
  // anything to say or do under the photo (an album's); a person's photo has the × alone
  const acts = $derived(!!list[at] && (!!list[at].by || !!list[at].event || !list[at].mine || (!!onremove && list[at].canDelete)));
  const shown = $derived(chrome && !dy && z === 1);

  async function remove() {
    const p = list[at];
    if (!p || !onremove || !(await sheets.ask({ title: t(data.galleryPost ? 'gallery.deleteAsk' : 'album.removeAsk'), ok: t(data.galleryPost ? 'gallery.delete' : 'album.remove'), cancel: t('common.cancel'), danger: true }))) return;
    const left = await onremove(p);
    if (!left) return;
    haptic.soft();
    if (!left.length) { close(overlay.id); return; }
    list = left; at = Math.min(at, left.length - 1);
  }
  // ⋯: report another's photo, delete mine (or any, for the club's Head+ in its album)
  function more(e: MouseEvent) {
    const p = list[at];
    if (!p) return;
    menu(e.currentTarget as Element, [
      ...(!p.mine ? [{ label: t('cm.report'), icon: Flag, onselect: report }] : []),
      ...(onremove && p.canDelete ? [{ label: t('gallery.delete'), icon: Trash, destructive: true, onselect: remove }] : []),
    ], 'end');
  }
  // the day it was taken; the year too when it isn't this one
  const when = (ts: number) => dayMonth(ts) + (parts(ts).y !== parts(nowTs()).y ? ` ${parts(ts).y}` : '');
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
  <div class="bd" bind:this={bd} style:opacity={1 - Math.min(dy, 300) / 360}></div>
  <div class="strip" class:zoomed={z > 1} role="presentation" bind:this={strip} onscroll={() => (at = Math.max(0, Math.min(list.length - 1, Math.round(strip.scrollLeft / strip.clientWidth))))}
    onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
    {#each list as p, i (p.id)}
      <!-- the small copy under the big one: on screen at once (it's the thumbnail just seen), sharp when the big one lands -->
      <div class="slide"><div class="pic" class:held={held && i === at} style:transform={i === at ? picMove : null}>
        <img src={p.thumb} alt="" decoding="async" draggable="false" loading={Math.abs(i - start) < 2 ? 'eager' : 'lazy'} />
        <img src={p.url} alt="" decoding="async" draggable="false" loading={i === start ? 'eager' : 'lazy'} />
      </div></div>
    {/each}
  </div>
  <div class="chrome" class:off={!shown}>
    {#if list.length > 1}
      <div class="film" bind:this={film} role="tablist">
        {#each list as p, i (p.id)}
          <button class="fr" class:on={i === at} role="tab" aria-selected={i === at} aria-label="{i + 1} / {list.length}" onclick={() => jump(i)}>
            <img src={p.thumb} alt="" loading="lazy" decoding="async" draggable="false" /></button>
        {/each}
      </div>
    {/if}
    {#if list[at]?.by || list[at]?.event}
      {@const p = list[at]}
      {@const ev = p.event}
      <div class="by" class:low={list.length < 2}>
        <!-- the Gallery's photos come from many events: the one this is from, a tap away -->
        {#if ev}<button class="ev" onclick={() => sheets.event(ev.id)}><span class="ellipsis">{ev.title}</span><ChevronRight size={14} strokeWidth={2.4} /></button>{/if}
        <!-- a Gallery post's author opens their profile (posted under their name) -->
        {#if p.by || p.at}<p>{#if p.by && p.uid}{@const uid = p.uid}<button class="who" onclick={() => sheets.person(uid)}>{p.by}</button>{:else if p.by}{p.by}{/if}{#if p.by && p.at}{' · '}{/if}{#if p.at}{when(p.at)}{/if}</p>{/if}
      </div>
    {/if}
    {#if data.galleryPost}
      {#if list[at] && (!list[at].mine || (onremove && list[at].canDelete))}
        <button class="tool r glass glass-pill" use:glass aria-label={t('common.more')} onclick={more}><Ellipsis size={22} /></button>
      {/if}
    {:else}
      <!-- the Gallery off (GALLERY): report and remove at the ×'s sides, as before -->
      {#if list[at] && !list[at].mine}<button class="tool l glass glass-pill" use:glass aria-label={t('cm.report')} onclick={report}><Flag size={20} /></button>{/if}
      {#if onremove && list[at]?.canDelete}<button class="tool r glass glass-pill danger" use:glass aria-label={t('album.remove')} onclick={remove}><Trash size={20} /></button>{/if}
    {/if}
  </div>
  <div class="chrome" class:off={!chrome || !!dy}><CloseX onclick={() => close(overlay.id)} /></div>
</div>

<style>
  .viewer { position: absolute; inset: 0; z-index: var(--z-sheet); color: #fff; }
  .bd { position: absolute; inset: 0; background: #000; }
  .strip { position: absolute; inset: 0; display: flex; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; overscroll-behavior: contain; scrollbar-width: none;
    touch-action: pan-x; }
  .strip::-webkit-scrollbar { display: none; }
  /* zoomed in: one finger pans the photo (ours), the strip holds still */
  .strip.zoomed { overflow-x: hidden; touch-action: none; }
  /* the photo fills the screen between the capsule and the ×; the chrome lies over it (a tap hides it) */
  .slide { flex: none; width: 100%; height: 100%; scroll-snap-align: center; scroll-snap-stop: always; padding: calc(var(--top) + 8px) 0 var(--close-room); }
  .pic { position: relative; width: 100%; height: 100%; transition: transform 320ms cubic-bezier(0.2, 0.85, 0.25, 1); will-change: transform; }
  .pic.held { transition: none; } /* under the fingers: no lag */
  .pic img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; display: block; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }

  .chrome { position: absolute; inset: 0; pointer-events: none; transition: opacity 200ms ease-out; }
  .chrome > :global(*) { pointer-events: auto; }
  .chrome.off { opacity: 0; }
  .chrome.off > :global(*) { pointer-events: none; }
  /* the filmstrip: small squares in a row, the one on show wider in the middle */
  .film { position: absolute; left: 0; right: 0; bottom: calc(var(--safe-bottom) + 84px); display: flex; align-items: center; gap: 2px; height: 46px;
    padding: 0 50%; overflow-x: auto; scrollbar-width: none; overscroll-behavior: contain; touch-action: pan-x; }
  .film::-webkit-scrollbar { display: none; }
  .fr { flex: none; width: 30px; height: 42px; padding: 0; overflow: hidden; background: rgba(255, 255, 255, 0.12); opacity: 0.75; -webkit-tap-highlight-color: transparent; }
  .fr img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .fr.on { width: 52px; height: 46px; margin: 0 4px; opacity: 1; }
  .by { position: absolute; left: 16px; right: 16px; bottom: calc(var(--safe-bottom) + 140px); text-align: center; font: 600 13px/1.2 var(--font-text);
    color: rgba(255, 255, 255, 0.8); text-shadow: 0 1px 4px rgba(0, 0, 0, 0.7); }
  .by.low { bottom: calc(var(--safe-bottom) + 84px); }
  .ev { display: inline-flex; align-items: center; gap: 2px; max-width: 100%; min-height: 32px; font: 600 var(--fs-body)/1.2 var(--font-text); color: inherit; text-shadow: inherit; }
  .ev > :global(svg) { flex: none; opacity: 0.7; }
  .ev:active { opacity: 0.6; }
  .who { display: inline; padding: 0; font: inherit; color: inherit; text-shadow: inherit; }
  .who:active { opacity: 0.6; }
  /* ⋯ (report, delete) at the ×'s side, as the phone's toolbar */
  .tool { position: absolute; bottom: calc(var(--safe-bottom) + 20px); width: 44px; height: 44px; display: grid; place-items: center; border-radius: var(--r-full);
    color: #fff; background-color: rgba(255, 255, 255, 0.12); }
  .tool > :global(svg) { position: relative; }
  .tool.l { left: 24px; }
  .tool.r { right: 24px; }
  .tool:active { transform: scale(0.94); }
  .danger { color: #FF8A80; background-color: rgba(255, 69, 58, 0.16); }
  @media (prefers-reduced-motion: reduce) { .pic, .chrome { transition: none; } }
</style>
