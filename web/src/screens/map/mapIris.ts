// How the campus map (CampusMap.svelte) comes and goes. Opened from the nav's round button (one with the bar), the map
// grows out of that circle and shrinks back into it: clip-path only, the map under it is painted once. Otherwise (no
// button, or reduced motion) it fades. Plain functions over the panel's elements; CampusMap calls them once each.
import { mapFrom } from '../../lib/state/sheets';
import { haptic } from '../../lib/tg';
import type { Overlay } from '../../lib/state/ui.svelte';

type Pt = { x: number; y: number };
export type MapIris = ((r: number) => string) & { at: Pt & { r: number }; el: HTMLElement | null };
const BACK_AFTER = 180; // ms into the iris: lands on the animation

/** the button the map was opened from, taken once as the map is made; null: it just fades in */
export function takeMapIris(): MapIris | null {
  const { at, el } = mapFrom; mapFrom.at = mapFrom.el = null;
  if (!at || matchMedia('(prefers-reduced-motion: reduce)').matches) return null;
  return Object.assign((r: number) => `circle(${r}px at ${at.x}px ${at.y}px)`, { at, el });
}

const reach = ({ x, y }: Pt) => Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));

// no capsule of ours over the map (owner, Nov 26: the whole screen is the map's; Telegram's own buttons stay): the
// circle's edge cuts the page's capsule, gone inside, there outside, either way. One live mask a frame, its place read
// once (it doesn't move meanwhile): a cloned glass copy of the capsule masked beside it doubled the work and stuttered
function veil(h: HTMLElement, c: Pt, done?: () => void) {
  const cap = document.querySelector<HTMLElement>('.cap');
  if (!cap) { done?.(); return; }
  const b = cap.getBoundingClientRect(), x = c.x - b.left, y = c.y - b.top;
  const frame = () => {
    if (!h.isConnected) { done?.(); cap.style.removeProperty('mask'); cap.style.removeProperty('-webkit-mask'); return; }
    const r = h.offsetWidth / 2, m = `radial-gradient(circle at ${x}px ${y}px, transparent ${r}px, #000 ${r}px)`;
    cap.style.setProperty('mask', m); cap.style.setProperty('-webkit-mask', m);
    requestAnimationFrame(frame);
  };
  frame();
}

// the circle's edge lit like the glass (without it the map "just takes over like a picture"): a ring
// of its own over the panel, its size animated with the clip (a scaled ring would thicken its line). Its look is
// CampusMap's global .map-halo
function halo(from: number, to: number, o: KeyframeAnimationOptions, opacity: number[], c: Pt): HTMLElement {
  const h = document.createElement('i');
  h.className = 'map-halo';
  h.style.cssText = `left:${c.x}px;top:${c.y}px`;
  document.body.append(h);
  h.animate({ width: [`${from * 2}px`, `${to * 2}px`], height: [`${from * 2}px`, `${to * 2}px`], opacity }, o).finished.catch(() => {}).finally(() => h.remove());
  return h;
}

/** no button to grow from: the panel fades in, our capsule fades away with it, then steps aside (overlay.bare); held
 *  faded till then, no flash between */
export function fadeIn(panel: HTMLElement, overlay: Overlay): void {
  panel.animate([{ opacity: 0, transform: 'scale(0.97)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.2,.9,.25,1)' });
  const fade = document.querySelector<HTMLElement>('.cap')?.animate({ opacity: [1, 0] }, { duration: 200, easing: 'ease-out', fill: 'forwards' });
  if (!fade) overlay.bare = true;
  else fade.finished.then(() => { overlay.bare = true; fade.cancel(); }, () => {});
}

/** the map grows out of the button's circle; returns the page under it, stepped back (closing brings it back) */
export function irisIn(iris: MapIris, panel: HTMLElement, stage: HTMLElement, overlay: Overlay, gone: () => boolean): { under: Animation | null; underEl: HTMLElement | null } {
  const o = { duration: 560, easing: 'cubic-bezier(.32, .8, .3, 1)' }, far = reach(iris.at);
  panel.animate({ clipPath: [iris(iris.at.r), iris(far)] }, o);
  // the map's own round button grows out of the one tapped (from the slim bar the small button and
  // the big one read as two buttons): it starts on the tapped one's place and size and settles on its own
  const shut = panel.querySelector<HTMLElement>('.shut'), sb = shut?.getBoundingClientRect();
  if (shut && sb?.width) shut.animate({ transform: [`translate(${iris.at.x - sb.left - sb.width / 2}px, ${iris.at.y - sb.top - sb.height / 2}px) scale(${(iris.at.r * 2) / sb.width})`, 'none'] }, o);
  // Telegram's Close turns into Back a moment into the circle, not at the tap nor at its end
  setTimeout(() => (overlay.holdBack = false), BACK_AFTER);
  // the map breathes out to meet you: a touch larger at first, it settles as the circle opens
  stage.animate({ transform: ['scale(1.08)', 'none'], transformOrigin: [`${iris.at.x}px ${iris.at.y - stage.offsetTop}px`, `${iris.at.x}px ${iris.at.y - stage.offsetTop}px`] }, o);
  // the page under it steps back (iOS's way): it stays put under the map, so it's clear the map came over it
  const underEl = document.querySelector<HTMLElement>('.app > .tab.on');
  const under = underEl?.animate(
    { transform: ['none', 'scale(0.94)'], opacity: [1, 0.45], transformOrigin: [`${iris.at.x}px ${iris.at.y}px`, `${iris.at.x}px ${iris.at.y}px`] }, { ...o, fill: 'forwards' }) ?? null;
  // once covered, the page under isn't drawn at all: held as a scaled, faded layer it kept its pictures and glass
  // composited under the map the whole visit; it shows again the moment the map starts closing
  under?.finished.then(() => { if (!gone() && underEl) underEl.style.visibility = 'hidden'; }, () => {});
  const h = halo(30, far, o, [1, 1, 1, 0], iris.at);
  // the circle wipes our capsule away as it passes; once it has covered the screen the capsule steps aside
  veil(h, iris.at, () => (overlay.bare = true));
  return { under, underEl };
}

/** no button: the panel fades out, our capsule fades back */
export function fadeOut(panel: HTMLElement): Animation {
  const a = panel.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
  document.querySelector<HTMLElement>('.cap')?.animate({ opacity: [0, 1] }, { duration: 200, easing: 'ease-out' });
  return a;
}

/** the map shrinks back into the button. `chrome` brings the capsule and the nav back, at the moment the circle
 *  starts uncovering them */
export function irisOut(iris: MapIris, panel: HTMLElement, stage: HTMLElement, under: Animation | null, underEl: HTMLElement | null, chrome: () => void): Animation {
  // eases out into the button (an ease-in close is fastest at its last frame and hits like a
  // hammer); the page under comes back on the same curve. The nav slides back in as it closes, so the opening's
  // point is stale and the circle would shrink off the button's centre: it closes on where the
  // button comes to rest, to the button's own size, and the button takes the ring's glow, then lets it fade
  const o = { duration: 480, easing: 'cubic-bezier(.45, 0, .2, 1)' };
  // back into the control it opened from (opened from Afisha's header, it closed into the bar's corner,
  // KRI's by then); that control gone from the page: the point it opened at. Only the bar's own button slides with its dock
  const b = iris.el?.isConnected ? iris.el : null, dock = b?.classList.contains('mapb') ? b.parentElement : null;
  const bt = b?.getBoundingClientRect(), dm = dock && getComputedStyle(dock).transform !== 'none' ? new DOMMatrix(getComputedStyle(dock).transform) : null;
  const c = bt ? { x: bt.left + bt.width / 2 - (dm?.e ?? 0), y: bt.top + bt.height / 2 - (dm?.f ?? 0) } : iris.at;
  const end = bt ? Math.min(bt.width, bt.height) / 2 : iris.at.r, far = reach(c);
  // the map's own button goes back into the one it came from (the bar stays as it was, slim or full)
  const shut = panel.querySelector<HTMLElement>('.shut'), sb = shut?.getBoundingClientRect();
  if (shut && sb?.width) shut.animate({ transform: ['none', `translate(${c.x - sb.left - sb.width / 2}px, ${c.y - sb.top - sb.height / 2}px) scale(${(end * 2) / sb.width})`] }, { ...o, fill: 'forwards' });
  const circle = (r: number) => `circle(${r}px at ${c.x}px ${c.y}px)`;
  const h = halo(far, end, o, [1, 1, 1], c); // held to the end: the ripples take over from it at the button's size
  veil(h, c); // the page's capsule comes back as the circle uncovers it (overlay.bare lets go with closing)
  chrome(); // the capsule and the nav come back now, the circle uncovers them
  stage.animate({ transform: ['none', 'scale(1.06)'] }, { ...o, fill: 'forwards' });
  underEl?.style.removeProperty('visibility');
  const page = document.querySelector<HTMLElement>('.app > .tab.on');
  if (under && page) {
    const u = under;
    page.animate({ transform: ['scale(0.94)', 'none'], opacity: [0.45, 1], transformOrigin: [`${c.x}px ${c.y}px`, `${c.x}px ${c.y}px`] }, o);
    u.cancel(); // the forwards hold goes, the new animation starts where it left the page
  }
  const a = panel.animate({ clipPath: [circle(far), circle(end)], opacity: [1, 1, 0] }, { ...o, fill: 'forwards' });
  // the button catches it: the ring lands on the button's
  // rim and goes on out as two soft ripples, the button gives under it and springs back, a glow swells inside it and
  // fades. Only opacity and transform move (the stepped box-shadow repainted every frame and read as steps).
  setTimeout(() => {
    haptic.tap();
    for (const [d, k] of [[0, 1.55], [130, 1.9]] as const) {
      const r = document.createElement('i');
      r.className = 'map-halo';
      r.style.cssText = `left:${c.x}px;top:${c.y}px;width:${end * 2}px;height:${end * 2}px`;
      document.body.append(r);
      r.animate({ transform: ['scale(1)', `scale(${k})`], opacity: [d ? 0.55 : 1, 0] }, { duration: 760, delay: d, easing: 'cubic-bezier(.2, .7, .3, 1)', fill: 'both' })
        .finished.catch(() => {}).finally(() => r.remove());
    }
    const g = document.createElement('i');
    g.className = 'map-glow';
    g.style.cssText = `left:${c.x}px;top:${c.y}px;width:${end * 3}px;height:${end * 3}px`;
    document.body.append(g);
    g.animate({ transform: ['scale(.5)', 'scale(1)', 'scale(1.15)'], opacity: [0, 1, 0], offset: [0, 0.3, 1] }, { duration: 820, easing: 'ease-out' })
      .finished.catch(() => {}).finally(() => g.remove());
    b?.animate([
      { transform: 'scale(1)' }, { transform: 'scale(.9)', offset: 0.22 }, { transform: 'scale(1.06)', offset: 0.55 },
      { transform: 'scale(.99)', offset: 0.8 }, { transform: 'scale(1)' },
    ], { duration: 680, easing: 'cubic-bezier(.3, .7, .4, 1)' });
  }, o.duration * 0.94);
  return a;
}
