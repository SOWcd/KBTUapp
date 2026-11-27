<script lang="ts">
  // An album full screen, as the phone's Photos: the photo grows out of the square it was
  // tapped in and shrinks back into the one it is on when it closes; a swipe goes to the next (the browser's own
  // scroll, its momentum and snapping), a pull down (the iOS gesture) drags the photo away (it shrinks, the black fades; far or fast
  // enough it closes into its square, else springs back); pinch or a double tap zooms at the fingers, a zoomed photo
  // pans with a rubber edge. A tap hides and shows the chrome: "3 / 12" in the capsule, the filmstrip (it follows the
  // photo, a finger along it scrubs, a tap jumps), who added it and when, and ⋯: report (another's: gone for me at once, the admin decides) and
  // delete (mine, or any for the club's Head+): in the web app the top-right pill is that one action (Overlay.action),
  // inside Telegram they stay at the bottom. Telegram's Back (or the app's own Back) or the pull down leaves. A person's lone photo
  // opens here too: a tap closes it. Every move is transform and opacity (clip-path in the flight).
  import { calm } from '../../ui/fold';
  import Images from '@lucide/svelte/icons/images';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Flag from '@lucide/svelte/icons/flag';
  import Trash from '@lucide/svelte/icons/trash-2';
  import { onMount, tick, untrack } from 'svelte';
  import { menu } from '../../ui/menu';
  import { singleAction } from '../../ui/guard';
  import { dayMonth, nowTs, parts } from '../../lib/time';
  import type { AlbumPhoto } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { data } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, inTelegram } from '../../lib/tg';
  import { glass } from '../../ui/glass';

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

  // The filmstrip, as the phone's Photos scrubs: `pos` is where it stands in photos (fractional), its centre is the
  // photo on show. A swipe of the big photo moves it with the scroll; a finger dragged along it scrubs (the photo
  // follows, a tick per photo, a fling coasts and settles), a tap jumps. The centred thumbnail widens to the photo's
  // own shape. Only the ones on screen exist (an album may hold hundreds); every move is a transform.
  const STEP = 32, TH = 40, NARROW = 30; // px: a thumbnail's slot, its height, its width when not centred
  let pos = $state(untrack(() => start)), fw = $state(0), scrubbing = $state(false), scrubFrom = $state(-1);
  let owned = false, near = -1, swallow = false, raf = 0, vel = 0, lastMv = { x: 0, t: 0 };
  let scrub: { x: number; p: number; id: number; moved: boolean } | null = null;
  const wideOf = (p: AlbumPhoto) => Math.max(22, Math.min(84, p.w && p.h ? (TH * p.w) / p.h : TH));
  // the two either side of pos share the widening by how near each is (one whole when centred, so it never jumps);
  // it takes a little room either side too, and the rest make way by half of what it grew
  const frames = $derived.by(() => {
    const n = list.length, half = Math.ceil(fw / 2 / STEP) + 3, a = Math.floor(pos), b = a + 1, c = Math.round(pos);
    const grow = (i: number) => { const f = i >= 0 && i < n ? 1 - Math.abs(i - pos) : 0; return f > 0 ? (wideOf(list[i]) - NARROW) * f : 0; };
    const ga = grow(a), gb = grow(b), ma = 8 * (1 - (pos - a)), mb = 8 * (pos - a);
    const out: { i: number; x: number; w: number }[] = [];
    for (let i = Math.max(0, c - half); i <= Math.min(n - 1, c + half); i++) {
      const x = (i - pos) * STEP + (i === a ? 0 : (Math.sign(i - a) * (ga + ma)) / 2) + (i === b ? 0 : (Math.sign(i - b) * (gb + mb)) / 2);
      out.push({ i, x, w: NARROW + (i === a ? ga : i === b ? gb : 0) });
    }
    return out;
  });
  // the film says which photo shows: the big strip jumps to it (instantly: it's under the finger) with a tick
  function place(p: number) {
    pos = Math.max(0, Math.min(list.length - 1, p));
    const i = Math.round(pos);
    if (i !== near) { near = i; strip.scrollLeft = i * strip.clientWidth; haptic.select(); }
  }
  function settle(to: number) {
    const from = pos, t0 = performance.now(), ms = calm() ? 0 : 220;
    const step = (t: number) => {
      const k = ms ? Math.min(1, (t - t0) / ms) : 1;
      place(from + (to - from) * (1 - (1 - k) ** 3));
      if (k < 1) raf = requestAnimationFrame(step);
      else { owned = false; scrubbing = false; }
    };
    cancelAnimationFrame(raf); raf = requestAnimationFrame(step);
  }
  function coast() {
    let prev = performance.now();
    const step = (t: number) => {
      const dt = t - prev; prev = t;
      vel *= 0.995 ** dt;
      place(pos + vel * dt);
      if (Math.abs(vel) > 0.003 && pos > 0 && pos < list.length - 1) raf = requestAnimationFrame(step);
      else settle(Math.round(pos));
    };
    raf = requestAnimationFrame(step);
  }
  function filmDown(e: PointerEvent) {
    if (scrub) return;
    cancelAnimationFrame(raf);
    swallow = false; owned = true; near = Math.round(pos); vel = 0;
    scrub = { x: e.clientX, p: pos, id: e.pointerId, moved: false };
    lastMv = { x: e.clientX, t: e.timeStamp };
  }
  function filmMove(e: PointerEvent) {
    if (!scrub || e.pointerId !== scrub.id) return;
    const d = e.clientX - scrub.x;
    if (!scrub.moved) {
      if (Math.abs(d) < 6) return;
      scrub.moved = true; scrubbing = true; scrubFrom = at;
      film?.setPointerCapture(e.pointerId);
    }
    place(scrub.p - d / STEP);
    const dt = Math.max(1, e.timeStamp - lastMv.t);
    vel = 0.7 * (-(e.clientX - lastMv.x) / STEP / dt) + 0.3 * vel; // photos per ms, a little smoothed
    lastMv = { x: e.clientX, t: e.timeStamp };
  }
  function filmUp(e: PointerEvent) {
    if (!scrub || e.pointerId !== scrub.id) return;
    const s = scrub;
    scrub = null;
    if (!s.moved) { owned = false; return; } // a tap: its click jumps
    swallow = true; // the click a drag ends with isn't a tap
    if (e.type !== 'pointerup' || e.timeStamp - lastMv.t > 80) vel = 0; // held still before letting go: no fling
    if (calm() || !vel) settle(Math.round(pos)); else coast();
  }
  function jump(i: number) {
    if (swallow) { swallow = false; return; }
    cancelAnimationFrame(raf);
    owned = true; near = Math.round(pos);
    settle(i);
  }
  // the big strip's own swipe moves the film with it, unless the film is the one moving
  function scrolled() {
    at = Math.max(0, Math.min(list.length - 1, Math.round(strip.scrollLeft / strip.clientWidth)));
    if (!owned) pos = Math.max(0, Math.min(list.length - 1, strip.scrollLeft / strip.clientWidth));
  }
  $effect(() => () => cancelAnimationFrame(raf));

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
    if (owned && !scrub) { cancelAnimationFrame(raf); owned = false; scrubbing = false; } // a finger on the photo stops a coasting film
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
  // anything to say or do under the photo (an album's); a person's photo has none
  const acts = $derived(!!list[at] && (!!list[at].by || !!list[at].event || !list[at].mine || (!!onremove && list[at].canDelete)));
  const shown = $derived(chrome && !dy && z === 1);

  const remove = singleAction(async () => {
    const p = list[at];
    if (!p || !onremove || !(await sheets.ask({ title: t(data.galleryPost ? 'gallery.deleteAsk' : 'album.removeAsk'), ok: t(data.galleryPost ? 'gallery.delete' : 'album.remove'), cancel: t('common.cancel'), danger: true }))) return;
    const left = await onremove(p);
    if (!left || overlay.closing) return;
    haptic.soft();
    if (!left.length) { close(overlay.id); return; }
    const selected = left.findIndex((photo) => photo.id === list[at]?.id);
    list = left; at = selected < 0 ? Math.min(at, left.length - 1) : selected;
    await tick();
    if (!overlay.closing) strip.scrollLeft = at * strip.clientWidth;
  });
  // ⋯: report another's photo, delete mine (or any, for the club's Head+ in its album); a single one is its own button
  const moreActs = $derived(list[at] ? [
    ...(!list[at].mine ? [{ label: t('cm.report'), icon: Flag, onselect: report }] : []),
    ...(onremove && list[at].canDelete ? [{ label: t(data.galleryPost ? 'gallery.delete' : 'album.remove'), icon: Trash, destructive: true, onselect: remove }] : []),
  ] : []);
  function more(e: MouseEvent) {
    if (moreActs.length === 1) moreActs[0].onselect();
    else menu(e.currentTarget as Element, moreActs, 'end');
  }
  // the web app: the top pill is the photo's one action (Report on another's), or ⋯ when it has both
  $effect(() => {
    if (inTelegram) return;
    const one = moreActs.length === 1 ? moreActs[0] : null;
    overlay.action = moreActs.length ? { icon: one ? one.icon : Ellipsis, label: one ? one.label : t('common.more'), run: more } : null;
  });
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
  <div class="strip" class:zoomed={z > 1} role="presentation" bind:this={strip} onscroll={scrolled}
    onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
    {#each list as p, i (p.id)}
      <!-- the small copy under the big one: on screen at once (it's the thumbnail just seen), sharp when the big one lands -->
      <div class="slide"><div class="pic" class:held={held && i === at} style:transform={i === at ? picMove : null}>
        <img src={p.thumb} alt="" decoding="async" draggable="false" loading={Math.abs(i - start) < 2 ? 'eager' : 'lazy'} />
        <!-- while scrubbing, the photos flown past show their small copy only: no full-size download for each -->
        {#if !scrubbing || i === scrubFrom}<img src={p.url} alt="" decoding="async" draggable="false" loading={i === start ? 'eager' : 'lazy'} />{/if}
      </div></div>
    {/each}
  </div>
  <div class="chrome" class:off={!shown} class:low={list.length < 2}>
    {#if list.length > 1}
      <div class="tray glass">
        <div class="film" bind:this={film} bind:clientWidth={fw} role="tablist" tabindex="-1"
          onpointerdown={filmDown} onpointermove={filmMove} onpointerup={filmUp} onpointercancel={filmUp}>
          {#each frames as f (list[f.i].id)}
            <button class="fr" role="tab" aria-selected={f.i === at} aria-label="{f.i + 1} / {list.length}" onclick={() => jump(f.i)}
              style:width="{f.w}px" style:transform="translate3d({f.x - f.w / 2}px, 0, 0)">
              <img src={list[f.i].thumb} alt="" decoding="async" draggable="false" style:background-color={list[f.i].color ?? null} /></button>
          {/each}
        </div>
      </div>
    {/if}
    {#if list[at]?.by || list[at]?.event}
      {@const p = list[at]}
      {@const ev = p.event}
      <div class="by">
        <!-- the Gallery's photos come from many events: the one this is from, a tap away -->
        {#if ev}<button class="ev" onclick={() => sheets.event(ev.id)}><span class="ellipsis">{ev.title}</span><ChevronRight size={14} strokeWidth={2.4} /></button>{/if}
        <!-- a Gallery post's author opens their profile (posted under their name) -->
        {#if p.by || p.at}<p>{#if p.by && p.uid}{@const uid = p.uid}<button class="who" onclick={() => sheets.person(uid)}>{p.by}</button>{:else if p.by}{p.by}{/if}{#if p.by && p.at}{' · '}{/if}{#if p.at}{when(p.at)}{/if}</p>{/if}
      </div>
    {/if}
    {#if !inTelegram}
      <!-- the web app: report and delete are the top pill's (above) -->
    {:else if data.galleryPost}
      {#if moreActs.length}
        {@const Icon = moreActs.length === 1 ? moreActs[0].icon : Ellipsis}
        <button class="tool r glass glass-pill" use:glass aria-label={moreActs.length === 1 ? moreActs[0].label : t('common.more')} onclick={more}><Icon size={moreActs.length === 1 ? 20 : 22} /></button>
      {/if}
    {:else}
      <!-- the Gallery off (GALLERY): report and remove at the caption's sides -->
      {#if list[at] && !list[at].mine}<button class="tool l glass glass-pill" use:glass aria-label={t('cm.report')} onclick={report}><Flag size={20} /></button>{/if}
      {#if onremove && list[at]?.canDelete}<button class="tool r glass glass-pill danger" use:glass aria-label={t('album.remove')} onclick={remove}><Trash size={20} /></button>{/if}
    {/if}
  </div>
</div>

<style>
  .viewer { position: absolute; inset: 0; z-index: var(--z-sheet); color: #fff; }
  .bd { position: absolute; inset: 0; background: #000; }
  .strip { position: absolute; inset: 0; display: flex; overflow-x: auto; overflow-y: hidden; scroll-snap-type: x mandatory; overscroll-behavior: contain; scrollbar-width: none;
    touch-action: pan-x; }
  .strip::-webkit-scrollbar { display: none; }
  /* zoomed in: one finger pans the photo (ours), the strip holds still */
  .strip.zoomed { overflow-x: hidden; touch-action: none; }
  /* the photo fills the screen between the capsule and the home bar; the chrome lies over it (a tap hides it) */
  .slide { flex: none; width: 100%; height: 100%; scroll-snap-align: center; scroll-snap-stop: always; padding: calc(var(--top) + 8px) 0 calc(var(--safe-bottom) + 8px); }
  .pic { position: relative; width: 100%; height: 100%; transition: transform 320ms cubic-bezier(0.2, 0.85, 0.25, 1); will-change: transform; }
  .pic.held { transition: none; } /* under the fingers: no lag */
  .pic img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; display: block; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }

  .chrome { position: absolute; inset: 0; pointer-events: none; transition: opacity 200ms ease-out; }
  .chrome > :global(*) { pointer-events: auto; }
  .chrome.off { opacity: 0; }
  .chrome.off > :global(*) { pointer-events: none; }
  /* the filmstrip: a calm glass tray (the viewer is black in both themes), slim thumbnails that fade out at its ends,
     the one on show at its true shape in the middle. Ours to drag (touch-action: none): a finger along it scrubs */
  .tray { position: absolute; left: 12px; right: 12px; bottom: calc(var(--safe-bottom) + 16px); height: 52px; border-radius: var(--r-s);
    background-color: rgba(255, 255, 255, 0.08); }
  .film { position: absolute; inset: 0; overflow: hidden; touch-action: none; border-radius: inherit;
    -webkit-mask-image: linear-gradient(90deg, transparent, black 12%, black 88%, transparent); mask-image: linear-gradient(90deg, transparent, black 12%, black 88%, transparent); }
  .fr { position: absolute; left: 50%; top: 6px; height: 40px; padding: 0; overflow: hidden; border-radius: calc(var(--r-xs) / 2); background: rgba(255, 255, 255, 0.12);
    will-change: transform; contain: strict; -webkit-tap-highlight-color: transparent; }
  .fr img { width: 100%; height: 100%; object-fit: cover; display: block; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; pointer-events: none; }
  /* above the filmstrip, one row: who added it in the middle, ⋯ (report, delete) at its sides, as the phone's toolbar;
     a lone photo (no strip) has that row at the bottom */
  .by, .tool { --row: calc(var(--safe-bottom) + 80px); }
  .low > .by, .low > .tool { --row: calc(var(--safe-bottom) + 16px); }
  .by { position: absolute; left: 76px; right: 76px; bottom: var(--row); min-height: 44px; display: flex; flex-direction: column; align-items: center; justify-content: center;
    text-align: center; font: 600 13px/1.2 var(--font-text); color: rgba(255, 255, 255, 0.8); text-shadow: 0 1px 4px rgba(0, 0, 0, 0.7); }
  .ev { display: inline-flex; align-items: center; gap: 2px; max-width: 100%; min-height: 32px; font: 600 var(--fs-body)/1.2 var(--font-text); color: inherit; text-shadow: inherit; }
  .ev > :global(svg) { flex: none; opacity: 0.7; }
  .ev:active { opacity: 0.6; }
  .who { display: inline; padding: 0; font: inherit; color: inherit; text-shadow: inherit; }
  .who:active { opacity: 0.6; }
  .tool { position: absolute; bottom: var(--row); width: 44px; height: 44px; display: grid; place-items: center; border-radius: var(--r-full);
    color: #fff; background-color: rgba(255, 255, 255, 0.12); }
  .tool > :global(svg) { position: relative; }
  .tool.l { left: 24px; }
  .tool.r { right: 24px; }
  .tool:active { transform: scale(0.94); }
  .danger { color: #FF8A80; background-color: rgba(255, 69, 58, 0.16); }
  @media (prefers-reduced-motion: reduce) { .pic, .chrome { transition: none; } }
</style>
