// Liquid glass behaviour. The look lives in base.css (.glass); this file adds what CSS can't:
//  1. The light follows the phone's tilt. One sensor serves all glass; --gx/--gy are written only on
//     registered elements and only while the light is still moving; the sensor stops when the app is hidden
//     and while power saving is on (state/power.svelte.ts).
//  2. A bloom from the touch point: a throwaway layer animated with opacity + transform (compositor only).
//  3. Real edge refraction where the engine supports SVG filters in backdrop-filter (Chromium: Telegram
//     Android and Desktop). WebKit ignores url() there, so iOS keeps the rim light only.
//  4. Jelly: squash-and-stretch of a sliding pill when it starts to move, leaning the way it goes.
import { deviceOrientation, on, tg } from '../lib/tg';
import { tiltFrom, upOf } from './tilt';

/** Telegram Android appends the device performance class to the User-Agent; LOW turns power saving on (in Auto) */
export const LOW = /;\s*LOW\)/.test(navigator.userAgent);

const lit = new Set<HTMLElement>();
const light = { x: 0, y: 0, tx: 0, ty: 0, n: null as number[] | null, at: 0, raf: 0, started: false, shown: '' };
const TAU = 3000; // ms: how fast neutral follows a new pose

/** Take the pose right now as neutral (a view that opens: it starts face on, however the phone is held) */
export function recenter(): void { light.n = null; light.tx = light.ty = light.x = light.y = 0; if (!light.raf && light.started) light.raf = requestAnimationFrame(paintLight); }

function paintLight() {
  light.raf = 0;
  light.x += (light.tx - light.x) * 0.12;
  light.y += (light.ty - light.y) * 0.12;
  const x = light.x.toFixed(2), y = light.y.toFixed(2);
  if (`${x},${y}` !== light.shown) {
    light.shown = `${x},${y}`;
    for (const n of lit) { n.style.setProperty('--gx', x); n.style.setProperty('--gy', y); }
  }
  if (Math.abs(light.tx - light.x) + Math.abs(light.ty - light.y) > 0.01) light.raf = requestAnimationFrame(paintLight);
}

const sensor = { allowed: true, run: () => {}, stop: () => {} };

function startTilt() {
  if (light.started) return;
  light.started = true;
  const d = deviceOrientation();
  if (!d || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  // refresh_rate is in ms: 50 = 20 Hz; the lerp in paintLight makes it smooth at 60 fps anyway
  sensor.run = () => { if (sensor.allowed) { try { d.start({ refresh_rate: 50 }); } catch { /* no gyro here */ } } };
  sensor.stop = () => { light.n = null; try { d.stop(); } catch { /* already off */ } };
  on('deviceOrientationChanged', () => {
    if (d.beta == null || d.gamma == null) return; // radians
    const [x, y, z] = upOf(d.beta, d.gamma), now = performance.now();
    // the way the phone is held is "neutral": taken when the sensor starts (or recenter()), then it follows the pose
    // with a few seconds' lag, so a steady hold settles face on and only movement tilts (owner, Nov 1: lying on his
    // side, a medal opened turned far away: gamma was read as absolute)
    if (!light.n || now - light.at > 1000) light.n = [x, y, z];
    else {
      const k = 1 - Math.exp(-(now - light.at) / TAU), n = light.n;
      n[0] += (x - n[0]) * k; n[1] += (y - n[1]) * k; n[2] += (z - n[2]) * k;
      const l = Math.hypot(n[0], n[1], n[2]) || 1; n[0] /= l; n[1] /= l; n[2] /= l;
    }
    light.at = now;
    // the turn from neutral to now (neutral × up: its axis, sin of its angle), on the screen's own axes: a pose
    // that's rolled by gravity (on one's side, in landscape) reads as no tilt at all
    const [tx, ty] = tiltFrom(light.n, [x, y, z], screen.orientation?.angle ?? 0);
    // a phone at rest still reads a few tenths of a degree of noise: below ~1 deg it is no move, nothing is written
    // (Android, Nov 2: the noise kept every glass and the award coin repainting 20 times a second, idle)
    if (Math.abs(tx - light.tx) + Math.abs(ty - light.ty) < 0.016) return;
    [light.tx, light.ty] = [tx, ty];
    if (!light.raf) light.raf = requestAnimationFrame(paintLight);
  });
  on('activated', () => sensor.run());
  on('deactivated', () => sensor.stop());
  sensor.run();
}

// Away and back: iOS drops the backdrop-filter layers of a hidden page and rebuilds them a few frames after the return,
// the glass showed bare. It goes solid as the app leaves (so the first frame back is already solid) and glides back to
// clear (base.css, 360 ms) once the blur is surely there again.
let wake: ReturnType<typeof setTimeout> | undefined;
const away = () => { clearTimeout(wake); document.documentElement.classList.add('glass-wake'); };
const back = () => { clearTimeout(wake); wake = setTimeout(() => document.documentElement.classList.remove('glass-wake'), 450); };
document.addEventListener('visibilitychange', () => (document.hidden ? away() : back()));
on('deactivated', away);
on('activated', back);

/** Power saving stops the light: the gyro, and a repaint of every glass element as the phone moves. */
export function tilt(allowed: boolean): void {
  sensor.allowed = allowed;
  if (allowed) sensor.run(); else sensor.stop();
}

function bloomAt(node: HTMLElement, e: PointerEvent) {
  const r = node.getBoundingClientRect();
  const b = document.createElement('span');
  b.className = 'glass-bloom';
  b.style.left = `${e.clientX - r.left}px`;
  b.style.top = `${e.clientY - r.top}px`;
  node.prepend(b); // after ::before (the sheen), before the content
  const a = b.animate?.([{ opacity: 1, transform: 'scale(0.35)' }, { opacity: 0, transform: 'scale(1.25)' }], { duration: 560, easing: 'cubic-bezier(.2,.7,.3,1)' });
  if (a) a.onfinish = () => b.remove(); else b.remove();
}

/** Svelte action for every glass element: tilt light, plus the touch bloom when `bloom` is set. */
export function glass(node: HTMLElement, opts: { bloom?: boolean } = {}) {
  lit.add(node);
  if (light.shown) { node.style.setProperty('--gx', light.x.toFixed(2)); node.style.setProperty('--gy', light.y.toFixed(2)); }
  startTilt();
  const down = (e: PointerEvent) => bloomAt(node, e);
  if (opts.bloom) node.addEventListener('pointerdown', down, { passive: true });
  return { destroy() { lit.delete(node); node.removeEventListener('pointerdown', down); } };
}

/** Edge displacement map for a pill: pixels near the rim are pushed along the edge normal. */
function lensMap(w: number, h: number): string {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d');
  if (!g) return '';
  const im = g.createImageData(w, h), d = im.data, r = h / 2, band = h * 0.42;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const dx = x - Math.min(Math.max(x, r), w - r), dy = y - r, dist = Math.hypot(dx, dy);
    const k = r - dist < band ? (1 - (r - dist) / band) ** 2 : 0;
    const o = (y * w + x) * 4;
    d[o] = 128 - (dist ? dx / dist : 0) * k * 127;
    d[o + 1] = 128 - (dist ? dy / dist : 0) * k * 127;
    d[o + 2] = 128; d[o + 3] = 255;
  }
  g.putImageData(im, 0, 0);
  return c.toDataURL();
}

/** Svelte action: real refraction at the edges of a pill-shaped glass element (Chromium only, not on
 *  phones Telegram marks as LOW performance). Sets --refract: the whole backdrop-filter, used with a
 *  fallback, `backdrop-filter: var(--refract, blur(…))`. */
export function refract(node: HTMLElement) {
  if (!/^(android|tdesktop)$/.test(tg.platform) || LOW || typeof ResizeObserver === 'undefined') return;
  const id = `kb-rf-${Math.random().toString(36).slice(2, 8)}`;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', '0'); svg.setAttribute('height', '0'); svg.setAttribute('aria-hidden', 'true');
  svg.style.position = 'absolute';
  svg.innerHTML = `<filter id="${id}" x="0" y="0" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB"><feImage result="m" x="0" y="0" preserveAspectRatio="none"/><feDisplacementMap in="SourceGraphic" in2="m" scale="26" xChannelSelector="R" yChannelSelector="G"/></filter>`;
  document.body.append(svg);
  const filter = svg.querySelector('filter')!, img = svg.querySelector('feImage')!;
  let size = '', timer: ReturnType<typeof setTimeout> | undefined;
  const build = () => {
    const w = Math.round(node.offsetWidth), h = Math.round(node.offsetHeight);
    if (!w || !h || `${w}x${h}` === size) return;
    size = `${w}x${h}`;
    const map = lensMap(w, h);
    if (!map) return;
    for (const el of [filter, img]) { el.setAttribute('width', String(w)); el.setAttribute('height', String(h)); }
    img.setAttribute('href', map);
    node.style.setProperty('--refract', `url(#${id}) blur(14px) saturate(210%) brightness(1.05)`);
  };
  // the nav changes size (mini mode): rebuild once the transition is over
  const ro = new ResizeObserver(() => { clearTimeout(timer); timer = setTimeout(build, 160); });
  ro.observe(node);
  build();
  return { destroy() { ro.disconnect(); clearTimeout(timer); svg.remove(); } };
}

/** Squash-and-stretch on a pill as it starts to slide. Uses transform, so put it on an element that
 *  isn't moved by transform itself. `d`: tabs travelled (signed): the stretch grows with the distance and leans the
 *  way the pill goes (anchored at its trailing edge, so the leading edge runs ahead like a drop), then settles from the
 *  middle; 0 squashes in place. None under reduced motion. */
export function jelly(el: HTMLElement | undefined, d = 0): void {
  if (!el?.animate || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const a = Math.min(Math.abs(d), 3), k = d ? 0.08 + 0.04 * a : 0.16;
  const o = d > 0 ? '0% 50%' : d < 0 ? '100% 50%' : '50% 50%';
  el.animate([
    { transform: 'scale(1, 1)', transformOrigin: o },
    { transform: `scale(${1 + k}, ${1 - k * 0.6})`, transformOrigin: o, offset: 0.32 },
    { transform: `scale(${1 - k * 0.18}, ${1 + k * 0.18})`, transformOrigin: '50% 50%', offset: 0.68 },
    { transform: 'scale(1, 1)', transformOrigin: '50% 50%' },
  ], { duration: 440 + a * 40, easing: 'cubic-bezier(.3, .7, .4, 1)' });
}
