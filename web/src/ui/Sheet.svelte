<script module lang="ts">
  // the rise's timing from the design tokens, read once for the app: a computed style read at every sheet's mount
  // restyled the document inside the tap that opened it
  let read: { rise: number; spring: string } | null = null;
  function tokens() {
    if (read) return read;
    const root = getComputedStyle(document.documentElement), slow = root.getPropertyValue('--t-slow').trim();
    return (read = { rise: (parseFloat(slow) || 0.38) * (slow.endsWith('ms') ? 1 : 1000), spring: root.getPropertyValue('--ease-spring').trim() || 'ease-out' });
  }
</script>

<script lang="ts">
  // Bottom sheet (liquid glass without the light spot, floats above everything). Closes by Telegram's Back button, a tap on the
  // scrim, or a pull down — from the grip, or from the content when it is scrolled to the top.
  // The drag writes transform directly (no reactive state per frame); exit runs, then the overlay
  // is removed from the stack.
  import type { Component, Snippet } from 'svelte';
  import { takeIris, irisOpen, irisShut } from '../lib/state/sheets';
  import { onMount, untrack } from 'svelte';
  import { keyboard, KB_MS, kbEase, riseMs } from '../lib/state/keyboard.svelte';
  import { removeOverlay, close, hideChrome, overlays, type Overlay } from '../lib/state/ui.svelte';
  import X from '@lucide/svelte/icons/x';
  import { haptic, inTelegram, onAndroid, tg } from '../lib/tg';
  import { t } from '../lib/i18n/index.svelte';
  import { glass } from './glass';
  import { unsent } from './guard';

  // heading: the sheet's title in its own header row, at the top, wrapping, never cut (the design system: 50 of 56 Russian
  // titles didn't fit the capsule at 320 px); the capsule then shows the sheet's icon alone. actions: that row's
  // buttons on the right (a Toolbar, a ⋯).
  // title: the old way, what the capsule says while this sheet is on top (SPEC §8.2); icon: a small mark before it
  // hold: while it says true, a close (Back, scrim, pull) is turned back — the sheet springs home and onhold runs (ask first).
  // Without one, text typed here and not sent asks before a hand closes it (a pull lost a club's application).
  // see: the page stays bright above it and the sheet takes at most the lower part, so what it changes shows live above
  // (my lanyard while I dress it)
  // shut: opened out of a round button (the iris), it closes back into that place, the same circle the other way; a
  // pull closes as a pull does, down from under the finger
  // Sizes by one rule: WORK (many steps, minutes: admin, registry, event management, forms) is `full`,
  // the whole screen under the capsule, closed by Back only (a pull must not drop work); LOOKING at one thing is `tall`,
  // up to the capsule; ONE DECISION is neither: as tall as its content.
  type Props = { overlay: Overlay; title?: string; heading?: string; actions?: Snippet; icon?: Component<any>; tint?: string | null; tall?: boolean; full?: boolean; see?: boolean; shut?: boolean;
    children: Snippet; footer?: Snippet; opener?: HTMLElement | null; hold?: () => boolean; onhold?: () => void };
  let { overlay, title = '', heading, actions, icon, tint = null, tall = false, full = false, see = false, shut = false, children, footer, opener, hold, onhold }: Props = $props();
  const iris = takeIris(); // opened out of a round button (lib/state/sheets irisFrom) instead of the rise
  $effect(() => { overlay.title = heading ?? title; overlay.icon = icon; overlay.mark = heading != null; });
  // opened over a tinted page (the event editor) without a tint of its own: the page's colour, not plain navy (owner, Nov 3)
  const ground = $derived(tint ? null : ([...overlays].reverse().find((o) => o.id < overlay.id && o.tint)?.tint ?? null));

  let panel: HTMLDivElement;
  let scrim: HTMLDivElement;
  let body: HTMLDivElement;
  let foot = $state<HTMLDivElement>();
  let room: HTMLDivElement;
  let gone = false;
  let scrolled = $state(false);
  // Android redraws a moving blur every frame of the rise (jank): the blur comes on once the sheet stands
  let rising = $state(tg.platform === 'android');
  // another overlay over this one: nothing in it moves (its loops, the tilt light, a lanyard's depth and its card). Android
  // re-blurs the top sheet's backdrop on every change under it: the event sheet over a friend's card shimmered (Nov 2)
  const under = $derived(overlays.some((o) => o.id > overlay.id && !o.closing));

  // the rise, and any height change after it, on one spring. The panel sits on the bottom edge, so a taller one would
  // put its top edge higher in one frame (details arriving after it opened: a person's card, a club); instead an added
  // offset holds the top edge where it was and lets it glide to its new place (FLIP), mid-rise or after. Its own
  // property (translate, added on), so the rise runs on untouched; the rise in pixels: a percentage of the height
  // would jump with it.
  let lift: Animation | null = null, height = 0;
  const motion = () => ({ duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : tokens().rise, easing: tokens().spring });
  // the first call comes after the browser's own layout and before the first paint: the rise starts there, with the
  // height already known (reading it at mount forced a layout of the whole sheet a step early)
  function resized() {
    const box = panel.getBoundingClientRect(), h = box.height, dh = h - height;
    if (!lift && iris) {
      height = h; lift = irisOpen(panel, iris);
      if (rising) lift.finished.catch(() => {}).finally(() => (rising = false));
      return;
    }
    if (!lift) {
      height = h; lift = panel.animate([{ transform: `translate3d(0,${h}px,0)` }, { transform: 'translate3d(0,0,0)' }], motion());
      if (rising) lift.finished.catch(() => {}).finally(() => (rising = false));
      return;
    }
    height = h;
    if (kbTo) { free = freeAbove(); place(kbNow); } // taller or shorter with the keyboard up: its share of it again
    if (Math.abs(dh) < 2 || gone || dragging || currentY) return;
    panel.animate([{ translate: `0 ${dh}px` }, { translate: '0 0' }], { ...motion(), composite: 'add' });
  }

  // ---- the keyboard (lib/state/keyboard): the box never follows it, what sits low rides up over it ----
  // A short sheet rises whole, as far as its top may go (iOS's own sheets); the rest of the keyboard (all of it for a
  // tall or full one) raises the footer over the body, which is clipped there and gets as much more room to scroll.
  // One tween on the keyboard's timing, retargeted as the steps come; inline styles on three boxes per frame, no
  // layout. A body whose end sat on its bottom edge (a chat, the assistant's greeting) keeps it there, above the footer.
  let kbNow = 0, kbFrom = 0, kbTo = 0, kbT0 = 0, kbEnd = 0, kbRaf = 0, free = 0, pinFrom = -1, pinMax = Infinity, natMax = 0, inFrom = 0, roomPx = 0;
  const innerOf = (k: number) => Math.max(0, k - free);
  function freeAbove() {
    if (full) return 0;
    const max = parseFloat(getComputedStyle(panel).maxHeight), parent = (panel.offsetParent as HTMLElement | null)?.clientHeight ?? 0;
    return Number.isFinite(max) && parent ? Math.max(0, panel.offsetTop - (parent - max)) : 0;
  }
  function setRoom(px: number) { if (px !== roomPx) { roomPx = px; body.style.setProperty('--kb-room', `${px}px`); } }
  function place(k: number) {
    const lift = Math.min(k, free), inner = k - lift;
    panel.style.translate = lift ? `0 ${-lift}px` : '';
    if (foot) { foot.style.translate = inner ? `0 ${-inner}px` : ''; body.style.clipPath = inner ? `inset(0 0 ${inner}px)` : ''; }
    // pinned: rides along; else never past what the room will allow (going down, the scroll eases back instead of
    // jumping when the room goes at the end)
    const cap = natMax + inner;
    if (pinFrom >= 0) body.scrollTop = Math.min(pinMax, cap, pinFrom + inner - inFrom);
    else if (body.scrollTop > cap) body.scrollTop = cap;
  }
  function ride(k: number) {
    if (!panel || gone || k === kbTo) return;
    const rest = !kbTo && !kbNow;
    if (rest) free = freeAbove(); // measured as it starts to rise, with the sheet at rest
    // a step while it moves (iOS and Android may report the keyboard in parts) finishes the same motion, not a new one.
    // A rise from rest counts from a frame back: the keyboard's first frame shows with ours, ours must not show nothing
    const now = performance.now() - (rest ? 16 : 0), ms = matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : k > kbNow ? riseMs() : KB_MS;
    kbEnd = kbNow !== kbTo && kbEnd > now ? Math.max(kbEnd, now + 120) : now + ms;
    kbFrom = kbNow; kbTo = k; kbT0 = now; inFrom = innerOf(kbNow);
    // pinned: the body's end (the room's top) right on its visible bottom, the raised footer's top
    const end = room.getBoundingClientRect().top, edge = body.getBoundingClientRect().bottom - parseFloat(getComputedStyle(body).paddingBottom) - inFrom;
    pinFrom = Math.abs(end - edge) < 10 ? body.scrollTop : -1;
    // ...but where its start is in view (the greeting over the starters), the start stays in view: what doesn't fit
    // goes under the footer, as it did when the box shrank
    const lead = body.querySelector(':scope > :first-child > :first-child') ?? body.firstElementChild, top = body.getBoundingClientRect().top + parseFloat(getComputedStyle(body).paddingTop);
    const at = lead ? lead.getBoundingClientRect().top - top : -1;
    pinMax = at >= 0 ? body.scrollTop + at : Infinity;
    natMax = Math.max(0, body.scrollHeight - body.clientHeight - roomPx);
    setRoom(Math.max(inFrom, innerOf(k))); // the larger room while it moves, so the pinned scroll never meets the end
    cancelAnimationFrame(kbRaf);
    const step = (now: number) => {
      const x = Math.min(1, Math.max(0, (now - kbT0) / (kbEnd - kbT0))); // a frame's time can be from before the call
      place((kbNow = kbFrom + (kbTo - kbFrom) * kbEase(x)));
      if (x < 1) kbRaf = requestAnimationFrame(step);
      else { setRoom(innerOf(kbTo)); pinFrom = -1; }
    };
    kbRaf = requestAnimationFrame(step);
  }
  // a sheet under another one gives the keyboard back (the top one rides)
  $effect(() => { const k = under ? 0 : keyboard.h; untrack(() => ride(k)); });

  function leave(fromY = 0) {
    if (gone) return;
    gone = true;
    lift?.cancel();
    if (shut && iris && !fromY && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      chrome(); chrome = () => {}; // the bar comes back now, its button under the closing circle
      const c = irisShut(panel, iris), ms = c.effect!.getComputedTiming().duration as number;
      scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: ms, easing: 'ease-in-out', fill: 'forwards' });
      c.onfinish = () => removeOverlay(overlay.id);
      return;
    }
    const h = panel.getBoundingClientRect().height;
    const a = panel.animate([{ transform: `translate3d(0,${fromY}px,0)` }, { transform: `translate3d(0,${h + 40}px,0)` }],
      { duration: 260, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }

  let chrome = () => {}; // gives the app's bars back (hideChrome)
  const guard = unsent(() => overlay);

  $effect(() => {
    if (!overlay.closing) return;
    if (hold ? hold() : guard.typed()) {
      overlay.closing = false;
      panel.style.transition = 'transform 320ms cubic-bezier(.32,.72,0,1)';
      panel.style.transform = 'translate3d(0,0,0)';
      currentY = 0;
      (hold ? onhold : guard.ask)?.();
      return;
    }
    leave(currentY);
  });

  // ---- pull to close ----
  let startX = 0, startY = 0, currentY = 0, dragging = false, decided = false, lastY = 0, lastT = 0, v = 0;
  function onStart(e: TouchEvent) {
    if (full || e.touches.length !== 1) return;
    const inBody = body.contains(e.target as Node);
    if (inBody && body.scrollTop > innerOf(kbNow)) return; // the list scrolls first (what the keyboard's room added is no scroll)
    if ((e.target as Element).closest?.('textarea, [role=slider]')) return; // a long text scrolls itself (dragging it closed the memo); a slider drags its own way
    startX = e.touches[0].clientX; startY = lastY = e.touches[0].clientY; lastT = performance.now(); v = 0;
    dragging = true; decided = false; currentY = 0;
    // blocking only while a pull may start: a passive scroll everywhere else (Android waited on every move, the scroll lagged)
    panel.addEventListener('touchmove', onMove, { passive: false });
  }
  const stop = () => { dragging = false; panel.removeEventListener('touchmove', onMove); };
  function onMove(e: TouchEvent) {
    if (!dragging) return;
    const y = e.touches[0].clientY, dy = y - startY;
    if (!decided) {
      const dx = e.touches[0].clientX - startX;
      if (Math.abs(dy) < 6 && Math.abs(dx) < 6) return;
      decided = true;
      if (dy < 0 || Math.abs(dx) > Math.abs(dy)) { stop(); return; } // upward: let the content scroll; sideways: a swipe of its own (a comment's reply)
      // a pull with the keyboard up drops it first, as native sheets do: the footer and the content go down with it
      // (the same ride as any blur) while the panel, all of it, follows the finger
      if (kbTo && panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    }
    if (e.cancelable) e.preventDefault();
    const now = performance.now();
    v = (y - lastY) / Math.max(1, now - lastT); lastY = y; lastT = now;
    currentY = Math.max(0, dy);
    panel.style.transition = 'none';
    panel.style.transform = `translate3d(0,${currentY}px,0)`;
  }
  function onEnd() {
    if (!dragging) return;
    stop();
    if (!decided) return;
    if (currentY > 120 || v > 0.6) { haptic.soft(); close(overlay.id, true); return; }
    panel.style.transition = 'transform 320ms cubic-bezier(.32,.72,0,1)';
    panel.style.transform = 'translate3d(0,0,0)';
    currentY = 0;
  }

  // keyboard and screen readers: focus goes into the sheet as it opens (unless a field in it took it) and back to what
  // opened it when it goes (never to a text field: that would bring the keyboard up)
  onMount(() => {
    // opener: what the tap focused, when a stand-in field took the focus before the sheet mounted (the assistant)
    const from = opener ?? document.activeElement as HTMLElement | null;
    // a frame later: focus needs the sheet laid out, and at mount that was a whole extra layout inside the tap (the frame
    // lays it out anyway right after)
    requestAnimationFrame(() => { if (panel.isConnected && !panel.contains(document.activeElement)) panel.focus({ preventScroll: true }); });
    const back = () => { if (from?.isConnected && !from.matches('input, textarea, [contenteditable]')) from.focus({ preventScroll: true }); };
    const ro = new ResizeObserver(resized);
    ro.observe(panel);
    panel.addEventListener('touchstart', onStart, { passive: true });
    panel.addEventListener('touchend', onEnd);
    panel.addEventListener('touchcancel', onEnd);
    panel.addEventListener('focusin', guard.focusin);
    chrome = hideChrome();
    return () => { ro.disconnect(); cancelAnimationFrame(kbRaf); chrome(); back(); };
  });
</script>

<div class="scrim" class:clear={see} bind:this={scrim} onclick={() => close(overlay.id, true)} role="presentation"></div>
<div class="sheet glass glass-sheet" use:glass class:tall class:full class:see class:hasfoot={!!footer} class:rising class:flat={onAndroid} class:under class:ground bind:this={panel} role="dialog" aria-modal="true" aria-label={title || undefined} tabindex="-1" style={tint ? `--tint:${tint}` : ground ? `--ground:${ground}` : ''}>
  {#if tint}<div class="tint" aria-hidden="true"></div>{/if}
  {#if !full}<div class="grip" aria-hidden="true"></div>
  {:else if !inTelegram}<button class="x" onclick={() => close(overlay.id, true)} aria-label={t('common.close')}><X size={22} /></button>{/if}<!-- no Back button in a browser: the only way out -->
  <!-- the scroll edge: what scrolls up fades out under the top (the grip, the capsule) instead of running into it -->
  <!-- (past the keyboard's room: the assistant's greeting lifted over the keyboard is not "scrolled under the top") -->
  <div class="body scroll" data-kb-own class:scrolled bind:this={body} onscroll={() => { if (scrolled !== body.scrollTop > 2 + roomPx) scrolled = !scrolled; }}>
    {#if heading != null}<header class="hd"><h2 class="hdt">{heading}</h2>{#if actions}<span class="hda">{@render actions()}</span>{/if}</header>{/if}
    {@render children()}
    <div class="kbroom" bind:this={room} aria-hidden="true"></div>
  </div>
  {#if footer}<div class="foot" bind:this={foot}>{@render footer()}</div>{/if}
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--scrim); animation: fade var(--t-base) ease-out both; }
  /* never above the capsule: outside Telegram (a browser) the top band is 0, the capsule still takes 46 px */
  .sheet {
    position: absolute; left: 0; right: 0; bottom: 0; z-index: var(--z-sheet);
    max-width: 560px; margin: 0 auto; max-height: calc(100% - max(var(--top), 48px) - 10px);
    display: flex; flex-direction: column; overflow: hidden; overflow: clip; /* clip: the browser's reveal of a focused field must not scroll the panel */
    border-radius: var(--r-xl) var(--r-xl) 0 0;
    will-change: transform;
  }
  .under, .under :global(*) { --gx: 0 !important; --gy: 0 !important; animation-play-state: paused !important; }
  .rising { -webkit-backdrop-filter: none !important; backdrop-filter: none !important; }
  /* Android (a user's video, Nov 6: the sheet's blur dropped tiles frame by frame, bands and whole cards blinked blank as a
     person's card opened over the member list): the sheet stays solid there, as under power saving. ponytail: no glass on
     Android sheets; a one-off blurred snapshot behind them is the upgrade */
  .flat { -webkit-backdrop-filter: none !important; backdrop-filter: none !important; background-color: var(--glass-solid); }
  .tall { height: calc(100% - max(var(--top), 48px) - 10px); }
  .sheet:focus { outline: none; }
  .full { top: 0; max-height: none; max-width: none; border-radius: 0; background: var(--glow), var(--bg); -webkit-backdrop-filter: none; backdrop-filter: none; }
  .full::before, .full::after { display: none; }
  .full .body { padding-top: var(--page-top); }
  .x { position: absolute; top: calc(var(--safe-top) + 4px); left: 12px; z-index: 1; width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--surface); color: var(--text); }
  .scrim.clear { background: transparent; }
  .see { max-height: 56%; }
  .tint {
    position: absolute; inset: 0 0 auto; height: 320px; pointer-events: none;
    background: linear-gradient(180deg, var(--tint), transparent);
    opacity: 0.5;
  }
  /* the tinted page's own colour (its tint under the ground's veil), so the sheet reads as part of it */
  .ground { background: linear-gradient(var(--tint-veil), var(--tint-veil)), var(--ground); --surface-solid: transparent; }
  .grip { position: relative; flex: none; width: 38px; height: 5px; border-radius: 3px; background: var(--line-2); margin: 8px auto 4px; }
  .body { position: relative; flex: 1; --pb: calc(var(--s-6) + var(--safe-bottom)); padding: 6px var(--gutter) var(--pb); scroll-padding-bottom: var(--kb-room, 0px); }
  /* (scroll-padding: a scrollIntoView to the end, the newest message, stops above the raised footer) */
  /* the keyboard's room to scroll: no height in the flow (a short sheet keeps its size), its box reaching that much past
     the end, the padding included, so the scroll goes exactly --kb-room further */
  .kbroom { height: calc(var(--kb-room, 0px) + var(--pb)); margin-bottom: calc(-1 * (var(--kb-room, 0px) + var(--pb))); pointer-events: none; }
  .foot {
    position: relative; flex: none; padding: var(--s-3) var(--gutter) calc(var(--s-3) + var(--safe-bottom));
    border-top: 1px solid var(--line);
  }
  /* a footer with nothing in it (its {#if} false: a club I'm in) is no bar at all: never an empty strip over the bottom (owner, Nov 3) */
  .foot:not(:has(*)) { display: none; }
  .hasfoot .body { --pb: var(--s-4); }
  .scrolled { -webkit-mask-image: linear-gradient(transparent, black 18px); mask-image: linear-gradient(transparent, black 18px); }
  .full .scrolled { -webkit-mask-image: linear-gradient(transparent calc(var(--head-bottom) - 4px), black var(--page-top));
    mask-image: linear-gradient(transparent calc(var(--head-bottom) - 4px), black var(--page-top)); }
  /* the heading row: the title wraps (a long word at its soft hyphen or the edge), the actions keep their place */
  .hd { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--s-3); margin: var(--s-1) 2px var(--s-4); }
  .hdt { min-width: 0; padding-top: 8px; font: 700 var(--fs-sec)/1.18 var(--font-display); letter-spacing: -0.018em; overflow-wrap: break-word; }
  .hda { flex: none; display: inline-flex; gap: var(--s-2); }
  @keyframes fade { from { opacity: 0; } }
</style>
