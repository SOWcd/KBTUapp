// The campus map's floor gestures (CampusMap.svelte): a drag along the floors' rail, or a sideways swipe on the map
// while it's zoomed out. The knob follows the finger while it drags (on the map: a page turn, the finger to the left
// goes a floor up); the floor changes on the let-go. The map owns the knob's place (kp) and the floor; this only
// works out where the finger puts them.
import { haptic } from '../../lib/tg';

export type SwipeHost = {
  /** the floors on the rail, in order */
  floors: () => number[];
  cur: () => number;
  /** one floor's width on the rail, px */
  knobWidth: () => number;
  /** the stage's width, px */
  stageWidth: () => number;
  /** the knob's place, in floors along the rail (fractional while dragged) */
  kp: () => number;
  setKp: (p: number) => void;
  setDragging: (on: boolean) => void;
  goTo: (floor: number) => void;
  /** the knob springs back into its place (the jelly squash) */
  settle: () => void;
};
export type FloorSwipe = ReturnType<typeof floorSwipe>;

export function floorSwipe(host: SwipeHost) {
  let sw: { x0: number; y0: number; dx: number; on: boolean; hist: [number, number][]; rail: boolean; k0: number } | null = null;
  function start(px: number, py: number, rail = false) { sw = { x0: px, y0: py, dx: 0, on: false, hist: [], rail, k0: host.floors().indexOf(host.cur()) }; }
  /** a finger moved: true once it's a floor swipe (the caller then neither pans nor taps) */
  function move(px: number, py: number): boolean {
    if (!sw) return false;
    const dx = px - sw.x0, dy = py - sw.y0;
    if (!sw.on) {
      if (dx * dx + dy * dy < 100) return false;
      // on the map more sideways than up or down is a floor (a natural swipe runs a bit diagonal); up or down, nothing:
      // zoomed out the plan has nowhere to go. Along the rail only a clear drag
      if (Math.abs(dx) <= Math.abs(dy) * (sw.rail ? 2 : 1)) { sw = null; return false; }
      sw.on = true; host.setDragging(true);
    }
    sw.dx = dx;
    const now = performance.now();
    sw.hist.push([now, dx]);
    while (sw.hist.length > 2 && now - sw.hist[0][0] > 90) sw.hist.shift();
    const last = host.floors().length - 1, fb = host.knobWidth();
    // on the rail the knob stays under the finger; on the map a half screen's swipe is one floor, the other way
    let p = sw.rail ? sw.k0 + dx / fb : sw.k0 - Math.max(-1, Math.min(1, dx / (host.stageWidth() / 2)));
    if (p < 0) p = -(1 - 1 / (1 - p * 0.6)); else if (p > last) p = last + (1 - 1 / (1 + (p - last) * 0.6)); // a rubber band at the ends
    host.setKp(p);
    return true;
  }
  /** the finger let go (or a second came): to the nearest floor, a flick carrying it one further */
  function end(cancel = false) {
    const z = sw; sw = null;
    if (!z?.on) return;
    host.setDragging(false);
    const h = z.hist, floors = host.floors(), last = floors.length - 1, kp = host.kp();
    const vx = h.length > 1 ? (h[h.length - 1][1] - h[0][1]) / Math.max(16, h[h.length - 1][0] - h[0][0]) : 0;
    const fling = Math.abs(vx) > 0.4 ? Math.sign(vx) * (z.rail ? 0.4 : -0.6) : 0;
    const step = Math.round(kp + fling) - z.k0, far = Math.abs(kp - z.k0) > 0.5 || fling !== 0;
    const i = cancel ? z.k0 : Math.max(0, Math.min(last, z.rail ? z.k0 + step : far ? z.k0 + Math.sign(kp + fling - z.k0) : z.k0)); // the map: one floor a swipe
    if (i === z.k0) { if (!cancel && (kp < -0.15 || kp > last + 0.15)) haptic.rigid(); host.setKp(i); host.settle(); return; }
    host.goTo(floors[i]);
  }
  return { start, move, end };
}

/** the rail's own listeners (an action): a drag along it, or a tap on a floor (a drag's let-go isn't a tap, swiped()).
 *  Listeners in code: the rail stays a plain tablist for the screen reader. `off`: no dragging (on the way) */
export function railGestures(s: FloorSwipe, off: () => boolean) {
  let swiped = false;
  const down = (e: PointerEvent) => { if (off()) return; swiped = false; s.start(e.clientX, e.clientY, true); };
  function move(e: PointerEvent) {
    if (!s.move(e.clientX, e.clientY)) return;
    // held only once it's a drag: captured from the start, a tap's click would go to the rail, not the floor's button
    if (!swiped) (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    swiped = true;
  }
  const up = () => s.end();
  function swipeable(el: HTMLElement) {
    const on = [['pointerdown', down], ['pointermove', move], ['pointerup', up], ['pointercancel', up]] as const;
    on.forEach(([k, f]) => el.addEventListener(k, f as EventListener));
    return { destroy: () => on.forEach(([k, f]) => el.removeEventListener(k, f as EventListener)) };
  }
  return { swipeable, swiped: () => swiped };
}
