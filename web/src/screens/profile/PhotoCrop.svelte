<script lang="ts">
  // A new photo of me (or a club's logo), framed before it's sent, like iOS's "Move and Scale" (students asked, Nov 2-3):
  // drag to move, pinch or the wheel to zoom around the fingers, a double tap resets; the window has the lanyard's
  // rounded square. Choose sends that square (≤1024 px, JPEG; the server keeps 1600). The × or Back cancels.
  // The photo is decoded off the main thread, upright by its EXIF, and shrunk to ≤3000 px first (a 48 MP photo would
  // freeze the phone); a gesture writes one transform per frame, no layout. The math: lib/crop.ts.
  import { onMount } from 'svelte';
  import CloseX from '../../ui/CloseX.svelte';
  import Button from '../../ui/Button.svelte';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { clampView, cropRect, zoomAt, type View } from '../../lib/crop';
  import ImageIcon from '@lucide/svelte/icons/image';

  let { overlay, file, done }: { overlay: Overlay; file: Blob; done: (b: Blob | null) => void } = $props();
  $effect(() => { overlay.title = t('look.crop'); overlay.icon = ImageIcon; overlay.theme = 'dark'; });

  const MAX_SIDE = 3000, OUT = 1024;
  let stage = $state<HTMLDivElement>();
  let pic = $state<HTMLCanvasElement>();
  let box = $state(300);                   // the window's side, px
  let w = $state(0), h = $state(0);        // the photo's size as decoded (shrunk)
  const base = $derived(w && h ? box / Math.min(w, h) : 1);
  let v: View = { zoom: 1, x: 0, y: 0 };   // not $state: a gesture paints it itself, once a frame
  let result: Blob | null = null, gone = false;

  // upright and shrunk; createImageBitmap off the main thread, an <img> where its options aren't known
  async function decode(): Promise<CanvasImageSource & { width: number; height: number }> {
    try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); } catch { /* old WebViews */ }
    const url = URL.createObjectURL(file), img = new Image();
    img.src = url;
    try { await img.decode(); return Object.assign(img, { width: img.naturalWidth, height: img.naturalHeight }); } finally { URL.revokeObjectURL(url); }
  }

  onMount(() => {
    const fit = () => { box = Math.min(320, innerWidth - 48, innerHeight - 300); v = clampView(w || 1, h || 1, box, v); paint(); };
    fit();
    addEventListener('resize', fit);
    const back = hideChrome();
    decode().then((src) => {
      if (gone || !pic) return;
      const k = Math.min(1, MAX_SIDE / Math.max(src.width, src.height));
      pic.width = Math.round(src.width * k); pic.height = Math.round(src.height * k);
      const g = pic.getContext('2d')!;
      g.imageSmoothingQuality = 'high';
      g.drawImage(src, 0, 0, pic.width, pic.height);
      if ('close' in src) src.close();
      w = pic.width; h = pic.height;
      paint();
    }).catch(() => { haptic.error(); say(t('look.badPhoto'), 'warning_3d'); close(overlay.id); });
    // the wheel: not passive, or the page would scroll instead; a trackpad's pinch comes as the wheel with ctrl
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      if (!w) return;
      const dy = e.deltaY * (e.deltaMode === 1 ? 16 : 1);
      const r = stage!.getBoundingClientRect();
      v = zoomAt(w, h, box, v, Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.002)), e.clientX - r.left - box / 2, e.clientY - r.top - box / 2);
      paint();
    };
    stage!.addEventListener('wheel', wheel, { passive: false });
    return () => { removeEventListener('resize', fit); stage?.removeEventListener('wheel', wheel); back?.(); };
  });

  let frame = 0;
  function paint() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (pic) pic.style.transform = `translate(-50%, -50%) translate(${v.x}px, ${v.y}px) scale(${v.zoom})`;
    });
  }

  // ---- the gestures: one finger moves, two zoom around their middle and move with it ----
  const pts = new Map<number, { x: number; y: number }>();
  let mid = { x: 0, y: 0 }, span = 0, centre = { x: 0, y: 0 }, travel = 0, downAt = 0, lastTap = { t: 0, x: 0, y: 0 };
  let easing = $state(false);
  const pair = () => {
    const [a, b] = [...pts.values()];
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, d: Math.hypot(a.x - b.x, a.y - b.y) };
  };
  function down(e: PointerEvent) {
    if (!w) return;
    stage!.setPointerCapture(e.pointerId);
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    easing = false;
    if (pts.size === 1) {
      const r = stage!.getBoundingClientRect();   // once a gesture, never in the loop
      centre = { x: r.left + box / 2, y: r.top + box / 2 };
      travel = 0; downAt = e.timeStamp;
    }
    if (pts.size === 2) { const p = pair(); mid = p; span = p.d; }
  }
  function move(e: PointerEvent) {
    const p = pts.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    p.x = e.clientX; p.y = e.clientY;
    travel += Math.abs(dx) + Math.abs(dy);
    if (pts.size === 1) v = clampView(w, h, box, { ...v, x: v.x + dx, y: v.y + dy });
    else if (pts.size === 2) {
      const q = pair();
      if (span) v = zoomAt(w, h, box, v, q.d / span, q.x - centre.x, q.y - centre.y);
      v = clampView(w, h, box, { ...v, x: v.x + q.x - mid.x, y: v.y + q.y - mid.y });
      mid = q; span = q.d;
    }
    paint();
  }
  function up(e: PointerEvent) {
    if (!pts.delete(e.pointerId)) return;
    if (pts.size === 1) { span = 0; return; }       // the other finger carries on moving
    if (pts.size || e.type === 'pointercancel' || travel > 10 || e.timeStamp - downAt > 300) return;
    // a tap: the second one in a row puts the photo back as it came
    if (e.timeStamp - lastTap.t < 320 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30) {
      lastTap.t = 0;
      if (v.zoom !== 1 || v.x || v.y) { easing = true; v = clampView(w, h, box, { zoom: 1, x: 0, y: 0 }); paint(); haptic.tap(); }
    } else lastTap = { t: e.timeStamp, x: e.clientX, y: e.clientY };
  }

  async function choose() {
    if (!pic || !w) return;
    const r = cropRect(w, h, box, v), side = Math.min(OUT, Math.round(r.side));
    const c = document.createElement('canvas');
    c.width = c.height = side;
    const g = c.getContext('2d')!;
    g.imageSmoothingQuality = 'high';
    g.fillStyle = 'white'; g.fillRect(0, 0, side, side);   // a transparent PNG on white, not on black (JPEG)
    g.drawImage(pic, r.sx, r.sy, r.side, r.side, 0, 0, side, side);
    result = await new Promise<Blob | null>((ok) => c.toBlob(ok, 'image/jpeg', 0.9));
    haptic.ok();
    close(overlay.id);
  }

  $effect(() => {
    if (!overlay.closing || gone) return;
    gone = true;
    if (frame) cancelAnimationFrame(frame);
    done(result);
    removeOverlay(overlay.id);
  });
</script>

<div class="crop">
  <div class="stage" bind:this={stage} style:width="{box}px" style:height="{box}px" role="presentation"
       onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
    <canvas bind:this={pic} class:easing class:ready={w > 0} style:width="{w * base}px" style:height="{h * base}px"></canvas>
    <span class="ring" aria-hidden="true"></span>
  </div>
  <p class="tip t-foot">{t('look.cropTip')}</p>
  <div class="go"><Button kind="filled" size="l" full onclick={choose} disabled={!w}>{t('look.cropDone')}</Button></div>
  <CloseX onclick={() => close(overlay.id)} />
</div>

<style>
  .crop { position: absolute; inset: 0; z-index: var(--z-sheet); background: black; display: flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 18px; padding: var(--top) 24px var(--close-room); overflow: hidden; }
  .stage { position: relative; touch-action: none; cursor: grab; }
  .stage:active { cursor: grabbing; }
  .stage canvas { position: absolute; left: 50%; top: 50%; max-width: none; transform: translate(-50%, -50%); transform-origin: center;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; pointer-events: none; opacity: 0; transition: opacity 0.2s; }
  .stage canvas.ready { opacity: 1; }
  .stage canvas.easing { transition: opacity 0.2s, transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1); }
  @media (prefers-reduced-motion: reduce) { .stage canvas, .stage canvas.easing { transition: none; } }
  :global(html.lowfx) .stage canvas.easing { transition: none; }
  /* the lanyard's rounded square clear (Hero: 18 px on 74), the rest of the photo dimmed: the shadow paints outside it */
  .ring { position: absolute; inset: 0; border-radius: 24%; pointer-events: none; box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.62), inset 0 0 0 1.5px rgba(255, 255, 255, 0.85); }
  .tip { position: relative; margin: 0; color: rgba(255, 255, 255, 0.7); text-align: center; }
  .go { position: relative; width: min(320px, 100%); }
</style>
