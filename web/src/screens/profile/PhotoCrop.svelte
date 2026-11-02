<script lang="ts">
  // A new photo of me, framed before it's sent (a student asked, Nov 2): drag to move, pinch (or the wheel) to zoom
  // inside a circle; Done sends that square, 1024 px, JPEG. The × or Back cancels. The canvas reads the <img> as
  // shown (EXIF-rotated), so the crop is what the circle showed.
  import { onMount, untrack } from 'svelte';
  import CloseX from '../../ui/CloseX.svelte';
  import Button from '../../ui/Button.svelte';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import ImageIcon from '@lucide/svelte/icons/image';

  let { overlay, file, done }: { overlay: Overlay; file: Blob; done: (b: Blob | null) => void } = $props();
  $effect(() => { overlay.title = t('look.crop'); overlay.icon = ImageIcon; overlay.theme = 'dark'; });

  const url = untrack(() => URL.createObjectURL(file));  // one photo per crop: the overlay never gets another
  let img = $state<HTMLImageElement>();
  let box = $state(300);                   // the circle's side, px
  let w = $state(0), h = $state(0);        // the photo's own size
  let zoom = $state(1), x = $state(0), y = $state(0);  // the photo's centre off the circle's, px
  const k = $derived(w && h ? (box / Math.min(w, h)) * zoom : 1);  // screen px per photo px; zoom 1 fills the circle
  let result: Blob | null = null, gone = false;

  onMount(() => {
    const fit = () => (box = Math.min(320, innerWidth - 48, innerHeight - 300));
    fit();
    addEventListener('resize', fit);
    const back = hideChrome();
    return () => { removeEventListener('resize', fit); back?.(); URL.revokeObjectURL(url); };
  });

  // the photo always covers the circle
  function clamp() {
    const mx = Math.max(0, (w * k - box) / 2), my = Math.max(0, (h * k - box) / 2);
    x = Math.min(mx, Math.max(-mx, x)); y = Math.min(my, Math.max(-my, y));
  }
  function zoomTo(z: number) {
    const was = zoom;
    zoom = Math.min(5, Math.max(1, z));
    x *= zoom / was; y *= zoom / was;      // around the circle's centre
    clamp();
  }

  const pts = new Map<number, { x: number; y: number }>();
  let pinch = 0;
  const gap = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
  function down(e: PointerEvent) {
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2) pinch = gap();
  }
  function move(e: PointerEvent) {
    const p = pts.get(e.pointerId);
    if (!p) return;
    if (pts.size === 1) { x += e.clientX - p.x; y += e.clientY - p.y; clamp(); }
    p.x = e.clientX; p.y = e.clientY;
    if (pts.size === 2) { const d = gap(); if (pinch) zoomTo(zoom * (d / pinch)); pinch = d; }
  }
  function up(e: PointerEvent) { pts.delete(e.pointerId); pinch = 0; }

  async function finish() {
    if (!img || !w) return;
    const side = 1024, src = box / k;
    const sx = w / 2 - (box / 2 + x) / k, sy = h / 2 - (box / 2 + y) / k;
    const c = document.createElement('canvas');
    c.width = c.height = side;
    const g = c.getContext('2d')!;
    g.fillStyle = 'white'; g.fillRect(0, 0, side, side);
    g.drawImage(img, sx, sy, src, src, 0, 0, side, side);
    result = await new Promise<Blob | null>((ok) => c.toBlob(ok, 'image/jpeg', 0.9));
    haptic.ok();
    close(overlay.id);
  }

  $effect(() => {
    if (!overlay.closing || gone) return;
    gone = true;
    done(result);
    removeOverlay(overlay.id);
  });
</script>

<div class="crop">
  <div class="stage" style:width="{box}px" style:height="{box}px" role="presentation"
       onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}
       onwheel={(e) => { e.preventDefault(); zoomTo(zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08)); }}>
    <img bind:this={img} src={url} alt="" draggable="false"
         onload={() => { w = img!.naturalWidth; h = img!.naturalHeight; }}
         style:width="{w * k}px" style:height="{h * k}px"
         style:transform="translate(calc(-50% + {x}px), calc(-50% + {y}px))" />
    <span class="ring" aria-hidden="true"></span>
  </div>
  <p class="tip t-foot">{t('look.cropTip')}</p>
  <div class="go"><Button kind="filled" size="l" full onclick={finish} disabled={!w}>{t('common.save')}</Button></div>
  <CloseX onclick={() => close(overlay.id)} />
</div>

<style>
  .crop { position: absolute; inset: 0; z-index: var(--z-sheet); background: black; display: flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 18px; padding: var(--top) 24px var(--close-room); }
  .stage { position: relative; touch-action: none; cursor: grab; overflow: visible; }
  .stage img { position: absolute; left: 50%; top: 50%; max-width: none; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; pointer-events: none; }
  /* the circle clear, the rest of the photo dimmed: the shadow paints outside it */
  .ring { position: absolute; inset: 0; border-radius: 50%; pointer-events: none; box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.62), inset 0 0 0 1.5px rgba(255, 255, 255, 0.85); }
  .tip { position: relative; margin: 0; color: rgba(255, 255, 255, 0.7); text-align: center; }
  .go { position: relative; width: min(320px, 100%); }
</style>
