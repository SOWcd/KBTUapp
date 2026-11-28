// The campus map's camera (CampusMap.svelte). The camera is MapLibre's (our own pan and zoom "perceived gestures
// badly"): it draws the floor's tiles of the level the size on screen needs, a finer level fading in over the coarser
// one, and the labels, which fade in and out as they find room. Here the plan's scale is 1 when it is as wide as the
// stage, up to MAX; a place on it is (u, v), fractions of its width and height (lib/mapgl.ts turns those into
// MapLibre's own). Plain functions over what the host hands in, read at the moment of each call.
import { LngLat, type Map as GLMap } from 'maplibre-gl';
import { lngLat, uvOf, zoomFor, widthAt, type Frame, type Ver } from '../../lib/mapgl';

export const MAX = 8;
// off at once, settles without a crawl: a critically damped spring (an easy ease is too slow, an
// ease-out one crawls at the end)
export const spring = (p: number) => (p >= 1 ? 1 : 1 - (1 + 10 * p) * Math.exp(-10 * p));
/** zoomed out: the whole floor, where one finger turns floors and never pans (the swipe "doesn't
 *  understand what I want"); a hair of zoom left by a pinch still counts, and the let-go takes it back (rest) */
const NEAR = 1.15;

export type CameraHost = {
  map: () => GLMap; fr: () => Frame; ver: () => Ver;
  stage: () => HTMLElement; side: () => HTMLElement; plan: () => HTMLElement; first: () => HTMLElement;
  /** fingers on the stage now */
  fingers: () => number;
};

export function camera(h: CameraHost) {
  const W = () => h.stage().clientWidth, H = () => h.stage().clientHeight;
  const scale = () => widthAt(h.fr(), h.map().getZoom()) / W();
  /** the camera that shows the plan at scale k with its (u, v) at the stage's (sx, sy) */
  function cam(k: number, u: number, v: number, sx = W() / 2, sy = H() / 2) {
    const fr = h.fr(), pw = W() * k;
    return { center: lngLat(fr, u + (W() / 2 - sx) / pw, v + (H() / 2 - sy) / (pw * fr.ar)), zoom: zoomFor(fr, pw) };
  }
  /** the plan's point under a point of the stage */
  function uvAt(px: number, py: number): [number, number] { const at = h.map().unproject([px, py]); return uvOf(h.fr(), at.lng, at.lat); }
  /** the screen's middle stays on the plan, so half a screen of room past each edge: a corner, or a route under the
   *  card, can be dragged to the middle; never smaller than the stage's width, never past MAX */
  function within(at: LngLat, zoom: number) {
    const fr = h.fr(), [u, v] = uvOf(fr, at.lng, at.lat), on = (n: number) => Math.min(1, Math.max(0, n));
    return { center: new LngLat(...lngLat(fr, on(u), on(v))), zoom: Math.min(zoomFor(fr, W() * MAX), Math.max(zoomFor(fr, W()), zoom)) };
  }
  /** what stands on the plan follows the camera: the overlay as wide as the plan is on screen (its pins keep their
   *  size), the overview under the canvas by a transform alone */
  function follow() {
    const fr = h.fr(), map = h.map(), p = map.project(lngLat(fr, 0, 0)), pw = widthAt(fr, map.getZoom()), plan = h.plan();
    plan.style.width = `${pw}px`; plan.style.transform = `translate3d(${p.x}px,${p.y}px,0)`;
    h.first().style.transform = `translate3d(${p.x}px,${p.y}px,0) scale(${pw / fr.fx / 512})`;
  }
  // the stage runs under Telegram's header (full-bleed); the plan rests below it, where .side starts
  const head = () => h.side().offsetTop - 10;
  /** the view a floor opens in: on the main map the building (u .12-.85 of Uni-Q's sheet, white margins round it) fills
   *  the width, not far away; the drawn plans have no margins, the whole of them */
  const homeK = () => (h.ver() === 'main' ? 1.3 : 1);
  /** the building in the middle of what's under the header, at scale k: where the plan rests zoomed out */
  const middle = (k = homeK()) => cam(k, h.ver() === 'main' ? 0.485 : 0.5, 0.5, W() / 2, head() + (H() - head()) / 2);
  const out = () => scale() < homeK() * NEAR;
  /** a running glide stops where it is on screen (a finger, a floor, the other version came) */
  const halt = () => h.map().stop();
  function reset() { halt(); h.map().jumpTo(middle()); }
  /** a glide to the whole floor: a finger in the middle of it lands it at once (it was halfway, neither out nor in) */
  let fitting = false;
  function easeFit(to: { center: LngLat | [number, number]; zoom: number }, duration: number) {
    const map = h.map();
    fitting = true; map.once('moveend', () => (fitting = false));
    map.easeTo({ ...to, duration, easing: spring });
  }
  /** a finger came: a glide to the whole floor lands at once, any other glide stops where it is */
  function grab(primary: boolean) {
    if (fitting && primary) { fitting = false; h.map().jumpTo(middle(Math.min(scale(), homeK()))); } else halt();
  }
  /** fingers let the plan go: zoomed out it may rest only in the middle and goes back there, at the size they left it
   *  under the whole floor's, or at the whole floor's from a hair over it; zoomed in it stays where it was left */
  function rest() {
    if (h.fingers() || !out()) return;
    const map = h.map(), to = middle(Math.min(scale(), homeK())), a = map.project(to.center), b = map.project(map.getCenter());
    if (Math.hypot(a.x - b.x, a.y - b.y) > 0.5 || Math.abs(to.zoom - map.getZoom()) > 0.005) easeFit(to, 380);
  }
  return { W, H, scale, cam, uvAt, within, follow, head, homeK, middle, out, halt, reset, easeFit, grab, rest };
}
