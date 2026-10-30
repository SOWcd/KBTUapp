<script lang="ts">
  // The cover's focus (good covers matter more than any effect). One photo fills a tall Feed slide,
  // the wide event sheet and a square list thumbnail, so instead of one crop the organizer marks what matters
  // and every frame keeps that point in view (object-position). Tap or drag on the photo, or use the arrow keys;
  // the three frames below update live.
  import type { Media } from '../../lib/api';
  import { focusPos } from '../../lib/photo';
  import { t } from '../../lib/i18n/index.svelte';

  let { cover, onpick }: { cover: Media; onpick: (focus: [number, number]) => void } = $props();
  let img: HTMLImageElement;
  const fx = $derived(cover.focus?.[0] ?? 0.5), fy = $derived(cover.focus?.[1] ?? 0.5);
  const FRAMES = [['feed', 'ed.inFeed'], ['card', 'ed.inCard'], ['list', 'ed.inList']] as const;

  const put = (x: number, y: number) => {
    const c = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 1000) / 1000;
    onpick([c(x), c(y)]);
  };
  function pick(ev: PointerEvent) {
    const r = img.getBoundingClientRect();
    put((ev.clientX - r.left) / r.width, (ev.clientY - r.top) / r.height);
  }
  const KEYS: Record<string, [number, number]> = { ArrowLeft: [-0.05, 0], ArrowRight: [0.05, 0], ArrowUp: [0, -0.05], ArrowDown: [0, 0.05] };
</script>

<p class="tip">{t('ed.focusTip')}</p>
<div class="pick">
  <span class="wrap" role="slider" tabindex="0" aria-label={t('ed.focusTip')} aria-valuetext="{Math.round(fx * 100)}%, {Math.round(fy * 100)}%"
        aria-valuenow={Math.round(fx * 100)}
        onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pick(e); }}
        onpointermove={(e) => { if (e.buttons) pick(e); }}
        onkeydown={(e) => { const d = KEYS[e.key]; if (d) { e.preventDefault(); put(fx + d[0], fy + d[1]); } }}>
    <img bind:this={img} src={cover.url} alt="" draggable="false" />
    <span class="dot" style="left:{fx * 100}%;top:{fy * 100}%"></span>
  </span>
</div>
<div class="frames">
  {#each FRAMES as [k, label] (k)}
    <figure class={k}><span><img src={cover.thumb} alt="" style:object-position={focusPos(cover)} /></span><figcaption>{t(label)}</figcaption></figure>
  {/each}
</div>

<style>
  .tip { margin: -2px 4px 0; font: 500 12.5px/1.35 var(--font-text); color: var(--text-3); }
  .pick { display: flex; justify-content: center; padding: 10px; border-radius: var(--r-l); background: var(--surface-2); }
  .wrap { position: relative; display: block; touch-action: none; cursor: crosshair; border-radius: 12px; outline: none; }
  .wrap:focus-visible { box-shadow: 0 0 0 3px var(--accent); }
  .wrap img { display: block; max-width: 100%; max-height: 260px; border-radius: 12px; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
  /* a ring you can see on any photo: white with a dark halo */
  .dot { position: absolute; width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%; pointer-events: none;
    border: 3px solid #fff; box-shadow: 0 0 0 1.5px rgba(0, 0, 0, 0.45), inset 0 0 0 1.5px rgba(0, 0, 0, 0.45), 0 4px 12px rgba(0, 0, 0, 0.35);
    background: rgba(255, 255, 255, 0.18); transition: left 60ms linear, top 60ms linear; }

  .frames { display: flex; align-items: flex-end; justify-content: center; gap: 14px; }
  figure { display: flex; flex-direction: column; align-items: center; gap: 6px; margin: 0; }
  figure span { display: block; overflow: hidden; background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
  figure img { display: block; width: 100%; height: 100%; object-fit: cover; }
  .feed span { width: 58px; height: 124px; border-radius: 12px; }   /* a phone-tall Feed slide */
  .card span { width: 136px; height: 79px; border-radius: 12px; }   /* the event sheet's photo */
  .list span { width: 58px; height: 58px; border-radius: 14px; }    /* a list row */
  figcaption { font: 560 12px/1 var(--font-text); color: var(--text-2); }
</style>
