<script lang="ts">
  // Horizontal pages inside one tab, side by side and 1:1 under the finger, as Telegram's folders (until Oct 11 iOS
  // push style: the later page on top, the one under it at 30 %; the owner: "looks fine, but I don't like it, it should
  // be prettier and faster"). Physics, first tuned on iPhone in the prototype:
  //  - direction decided after 5 px, horizontal if |dx| > 0.7 |dy|; 3 px slop subtracted on lock
  //  - velocity averaged over the last ~90 ms; commit on a flick > 0.3 px/ms or a drag > 30 % width
  //  - settle 180–300 ms, its curve starting at the finger's speed; rubber band + rigid haptic at the edges
  // During a drag only transforms are written (no reactive state per frame); `index` changes once,
  // after the settle. Pages mount on first visit (the neighbours of the page on screen a moment after it shows,
  // so a first swipe never builds a page under the finger) and stay alive. A tab never shown builds nothing: at start
  // only the open tab's page (the hidden tabs were ~1400 of 1900 nodes and 40 % of the blocking time).
  import type { Snippet } from 'svelte';
  import { onMount, untrack } from 'svelte';
  import { haptic } from '../lib/tg';

  type Props = { count: number; index: number; active?: boolean; onchange: (i: number) => void; page: Snippet<[number]> };
  let { count, index, active = true, onchange, page }: Props = $props();

  let root: HTMLDivElement;
  const els: HTMLDivElement[] = [];
  let visited = $state<boolean[]>([]);
  let shown = $state(false);
  $effect(() => { if (active && !shown) shown = true; });
  $effect(() => { if (!visited[index]) visited[index] = true; });

  let cur = 0;            // what the DOM shows right now (index can lag until the settle commits); set on mount
  let busy = false;
  let target = 0;         // where a running settle is heading
  let timer: ReturnType<typeof setTimeout> | undefined;
  function commit() { clearTimeout(timer); cur = target; busy = false; layout(0); onchange(cur); }

  // measured once per resize, not per frame (a forced layout on every frame of a drag); not innerWidth: from 600 px
  // the app is a 480 px column
  let w0 = 0;
  const W = () => w0 || (w0 = root.clientWidth || innerWidth);
  // position of page i when the strip is shifted by v px (v < 0 = moving to the next page)
  function place(i: number, v: number, w: number) {
    const el = els[i]; if (!el) return;
    const u = (i - cur) * w + v;
    el.style.transform = `translate3d(${u}px,0,0)`;
    // '' inherits: a page in a hidden tab stays hidden (an explicit 'visible' would show through)
    el.style.visibility = u > -w + 0.5 && u < w - 0.5 ? '' : 'hidden';
  }
  function layout(v: number, ease = '') {
    const w = W();
    for (let i = 0; i < count; i++) {
      const el = els[i]; if (!el) continue;
      el.style.transition = ease;
      place(i, v, w);
    }
    // the capsule's page switcher follows the finger; only the visible tab talks to it
    if (active) window.dispatchEvent(new CustomEvent('kb:pager', { detail: { x: cur - v / w, ease } }));
  }

  /** Animate to page i; commit index after the animation. */
  export function slideTo(i: number, ms = 300) {
    if (i === cur || i < 0 || i >= count) { layout(0, `transform ${ms}ms cubic-bezier(.2,.85,.25,1)`); return; }
    if (!visited[i]) visited[i] = true;
    busy = true; target = i;
    const d = i - cur;
    layout(-d * W(), `transform ${ms}ms cubic-bezier(.2,.85,.25,1)`);
    clearTimeout(timer);
    timer = setTimeout(commit, ms);
  }

  // pages added or removed (tab 2 after sign-in): place them at once — a new page left unplaced sits on
  // top of the others with its empty background. Only `count` may re-run this: layout() also reads
  // `active`, and re-running on a tab switch sent the capsule a snap (ease '') that killed its slide
  // whenever the new tab came earlier in the tree than the old one.
  $effect(() => {
    const n = count;
    if (!root) return;
    untrack(() => {
      if (cur > n - 1) cur = target = Math.max(0, n - 1);
      layout(0);
    });
  });

  // external index changes (capsule switcher, re-tapping the tab)
  $effect(() => { const i = index; if (i !== cur && !busy) slideTo(i); });

  $effect(() => {
    if (!active) return;
    const i = index;
    const id = setTimeout(() => { for (const j of [i - 1, i + 1]) if (j >= 0 && j < count && !visited[j]) visited[j] = true; }, 2000);
    return () => clearTimeout(id);
  });

  // ---- touch ----
  let tz: null | { x: number; y: number; lock: '' | 'x'; ox: number; dx: number; hist: [number, number][]; strip: HTMLElement | null } = null;
  function blocked(t: EventTarget | null) {
    const el = t as HTMLElement | null;
    return !!el?.closest?.('[data-noswipe], input, textarea, .hscroll');
  }
  function start(e: TouchEvent) {
    if (e.touches.length !== 1 || blocked(e.target)) { tz = null; return; }
    if (busy) commit(); // a touch during the settle finishes it at once instead of being ignored
    const t = e.touches[0];
    // a sideways strip (data-edge: a Feed slide's photos) scrolls itself; at its end the swipe moves the pages, as on TikTok
    tz = { x: t.clientX, y: t.clientY, lock: '', ox: 0, dx: 0, hist: [], strip: (e.target as HTMLElement | null)?.closest?.('[data-edge]') ?? null };
  }
  function move(e: TouchEvent) {
    if (!tz) return;
    if (e.touches.length > 1) { if (tz.lock) layout(0, 'transform 300ms cubic-bezier(.2,.9,.25,1)'); tz = null; return; }
    const t = e.touches[0];
    let dx = t.clientX - tz.x; const dy = t.clientY - tz.y;
    if (!tz.lock) {
      if (dx * dx + dy * dy < 25) return;
      const st = tz.strip;
      if (st && (dx < 0 ? st.scrollLeft + st.clientWidth < st.scrollWidth - 2 : st.scrollLeft > 2)) { tz = null; return; }
      if (Math.abs(dx) > Math.abs(dy) * 0.7 && count > 1) { tz.lock = 'x'; tz.ox = dx > 0 ? 3 : -3; }
      else { tz = null; return; }
    }
    if (e.cancelable) e.preventDefault();
    const now = performance.now();
    dx -= tz.ox; tz.dx = dx;
    tz.hist.push([now, dx]);
    while (tz.hist.length > 2 && now - tz.hist[0][0] > 90) tz.hist.shift();
    const dir = dx < 0 ? 1 : -1;
    const can = cur + dir >= 0 && cur + dir < count;
    if (can && !visited[cur + dir]) visited[cur + dir] = true;
    layout(can ? dx : (dx / (1 + Math.abs(dx) / 90)) * 0.6);
  }
  function end() {
    const z = tz; tz = null;
    if (!z || z.lock !== 'x') return;
    const h = z.hist;
    const vx = h.length > 1 ? (h[h.length - 1][1] - h[0][1]) / Math.max(16, h[h.length - 1][0] - h[0][0]) : 0;
    const dir = Math.abs(vx) > 0.3 ? (vx < 0 ? 1 : -1) : z.dx < 0 ? 1 : -1;
    const w = W();
    const can = cur + dir >= 0 && cur + dir < count;
    const go = can && (Math.abs(vx) > 0.3 ? (z.dx < 0) === (dir > 0) || Math.abs(z.dx) < 40 : Math.abs(z.dx) > w * 0.3);
    if (go) {
      haptic.select();
      // continue from where the finger left the pages, at its speed: the curve's first slope y1/x1 is v·T/D (a fixed
      // ease-out set off at 4x the finger and jumped ahead)
      const d = Math.abs(dir * w + z.dx), v = Math.max(0, -dir * vx);
      const ms = Math.round(Math.max(180, Math.min(300, (1.6 * d) / Math.max(v, 1))));
      const y1 = Math.max(0.25, Math.min(1, (0.25 * v * ms) / Math.max(d, 1)));
      busy = true; target = cur + dir;
      layout(-dir * w, `transform ${ms}ms cubic-bezier(.25,${y1.toFixed(2)},.25,1)`);
      clearTimeout(timer);
      timer = setTimeout(commit, ms);
    } else {
      if (!can) haptic.rigid();
      layout(0, 'transform 320ms cubic-bezier(.2,.9,.25,1.1)');
    }
  }

  onMount(() => {
    cur = target = index;
    layout(0);
    root.addEventListener('touchstart', start, { passive: true });
    root.addEventListener('touchmove', move, { passive: false });
    root.addEventListener('touchend', end);
    root.addEventListener('touchcancel', end);
    const onResize = () => { w0 = 0; layout(0); };
    addEventListener('resize', onResize);
    return () => removeEventListener('resize', onResize);
  });
</script>

<div class="pager" bind:this={root}>
  {#each { length: count } as _, i}
    <div class="pg" bind:this={els[i]}>
      {#if shown && (visited[i] || i === index)}{@render page(i)}{/if}
    </div>
  {/each}
</div>

<style>
  .pager { position: absolute; inset: 0; overflow: hidden; touch-action: pan-y; }
  .pg { position: absolute; inset: 0; contain: layout paint; backface-visibility: hidden; } /* clear: the app ground shows through */
</style>
