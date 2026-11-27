<script lang="ts">
  // One format of an event's cover at its real shape (the Feed's tall slide, the event's card, a list's thumbnail): the
  // photo is dragged inside the frame, or moved with the arrow keys, and what the frame shows is what that format will
  // show everywhere (object-position; lib/photo panFocus). No zoom: one gesture, nothing to learn.
  import Move from '@lucide/svelte/icons/move';
  import type { CoverFormat, Media } from '../../lib/api';
  import { focusPos, panFocus } from '../../lib/photo';
  import { sw } from '../../lib/i18n/staff';

  let { photo, fmt, onpick }: { photo: Media; fmt: CoverFormat; onpick: (focus: [number, number]) => void } = $props();
  let last: [number, number] | null = null;
  let moved = $state(false); // the hint goes with the first drag
  const at = $derived<[number, number]>(photo.focus ?? [0.5, 0.5]);

  function drag(ev: PointerEvent) {
    if (!last) return;
    const r = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    onpick(panFocus(at, ev.clientX - last[0], ev.clientY - last[1], photo, { w: r.width, h: r.height }));
    last = [ev.clientX, ev.clientY];
    moved = true;
  }
  const KEYS: Record<string, [number, number]> = { ArrowLeft: [-0.05, 0], ArrowRight: [0.05, 0], ArrowUp: [0, -0.05], ArrowDown: [0, 0.05] };
  const unit = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 1000) / 1000;
</script>

<div class="frame {fmt}" role="slider" tabindex="0" aria-label={sw('ed.cropTip')} aria-valuenow={Math.round(at[0] * 100)}
     aria-valuetext="{Math.round(at[0] * 100)}%, {Math.round(at[1] * 100)}%"
     onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); last = [e.clientX, e.clientY]; }}
     onpointermove={drag} onpointerup={() => (last = null)} onpointercancel={() => (last = null)}
     onkeydown={(e) => { const d = KEYS[e.key]; if (d) { e.preventDefault(); moved = true; onpick([unit(at[0] + d[0]), unit(at[1] + d[1])]); } }}>
  <img src={photo.url} alt="" draggable="false" style:object-position={focusPos(photo)} />
  {#if !moved}<span class="tip glass glass-pill"><Move size={15} strokeWidth={2.4} />{sw('ed.cropTip')}</span>{/if}
</div>

<style>
  .frame { position: relative; align-self: center; overflow: hidden; touch-action: none; cursor: grab; outline: none; background: var(--surface-2);
    border-radius: var(--r-l); box-shadow: var(--shadow-card), var(--card-rim); }
  .frame:active { cursor: grabbing; }
  .frame:focus-visible { box-shadow: 0 0 0 3px var(--accent); }
  .feed { height: min(54vh, 440px); aspect-ratio: 9 / 16; }
  .card { width: 100%; aspect-ratio: 16 / 10; }
  .list { width: 208px; aspect-ratio: 1; }
  img { display: block; width: 100%; height: 100%; object-fit: cover; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; pointer-events: none; }
  .tip { position: absolute; left: 50%; bottom: var(--s-3); translate: -50% 0; display: inline-flex; align-items: center; gap: 6px; padding: 7px var(--s-3);
    border-radius: var(--r-full); white-space: nowrap; font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text); pointer-events: none;
    animation: tip 320ms var(--ease) 200ms backwards; }
  @keyframes tip { from { opacity: 0; transform: translate3d(0, 6px, 0); } }
</style>
