// The campus map's own fingers on its stage (CampusMap.svelte). MapLibre drags, pinches around the fingers' middle
// and takes the wheel; ours on top of it: a hold in place (a long press marks "something's wrong here"), and while
// zoomed out the floor swipe (floorSwipe.ts) instead of a pan. The taps are MapLibre's click (CampusMap's tap).
import type { Map as GLMap } from 'maplibre-gl';
import type { FloorSwipe } from './floorSwipe';

type Pt = { x: number; y: number };
export type GestureHost = {
  stage: () => HTMLElement; map: () => GLMap; swipe: () => FloorSwipe;
  /** zoomed out: one finger turns floors and never pans */
  out: () => boolean;
  /** a finger came down (primary: the first of a new touch): whatever glides gives way */
  touch: (primary: boolean) => void;
  /** no hold now: on the way, or an end being tapped */
  busy: () => boolean;
  /** a hold in place fired at this point of the stage: true if it took it (a flaw is being marked) */
  hold: (at: Pt) => boolean;
  /** the finger is turning floors: not a tap */
  swiped: () => void;
};

export function stageGestures(h: GestureHost) {
  let fingers = 0, held = false;
  let press: Pt | null = null; // the first finger down, for a hold in place
  let holdT: ReturnType<typeof setTimeout> | undefined;
  const local = (e: PointerEvent) => { const r = h.stage().getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const eat = (e: Event) => { e.stopPropagation(); e.preventDefault(); };
  function down(e: PointerEvent) {
    h.touch(e.isPrimary);
    clearTimeout(holdT); held = false;
    // the first finger of a new touch: any finger still counted is stale (iOS sends no up for one held while the flaw's
    // sheet opened over it, so every later press read as a second finger and never held)
    fingers = e.isPrimary ? 1 : fingers + 1;
    if (!e.isPrimary) { press = null; h.swipe().end(true); h.map().dragPan.enable(); return; } // a second finger: a pinch, never a hold or a floor
    const at = (press = local(e)), id = e.pointerId;
    if (h.busy()) return; // on the way, or an end being tapped: no note held down
    // held: the finger is the stage's from here on, and the click its let-go may bring is swallowed, so neither lands
    // on the note's sheet that has just opened under the finger and shuts it
    holdT = setTimeout(() => {
      if (!h.hold(at)) return;
      held = true; press = null;
      try { h.stage().setPointerCapture(id); } catch { /* the finger is gone */ }
      window.addEventListener('click', eat, { capture: true, once: true });
    }, 600);
    // zoomed out one finger is ours alone: MapLibre doesn't pan (the plan would only spring back), a sideways move turns
    // the floor; a second finger gives the map back its pinch and pan
    if (h.out()) { h.map().dragPan.disable(); h.swipe().start(e.clientX, e.clientY); }
  }
  function move(e: PointerEvent) {
    if (!e.isPrimary || !press) return;
    const p = local(e);
    if (Math.hypot(p.x - press.x, p.y - press.y) > 8) clearTimeout(holdT); // it moved: not a hold
    if (h.swipe().move(e.clientX, e.clientY)) h.swiped();
  }
  function up(e: PointerEvent) {
    clearTimeout(holdT);
    if (held) setTimeout(() => window.removeEventListener('click', eat, true), 350); // no click came: the next one is a real one
    fingers = Math.max(0, fingers - 1);
    if (e.isPrimary) { press = null; h.swipe().end(); h.map().dragPan.enable(); }
  }
  return {
    down, move, up,
    fingers: () => fingers,
    /** the let-go of a hold is not a tap: true once, for the click that follows it */
    takeHeld: () => { const was = held; held = false; return was; },
    /** the map closing: no note's sheet opens over it */
    cancel: () => clearTimeout(holdT),
  };
}
