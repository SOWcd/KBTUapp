// Liquid glass behaviour. The look lives in base.css (.glass); this file adds what CSS can't:
//  1. The light follows the phone's tilt. One sensor serves all glass; --gx/--gy are written only on
//     registered elements and only while the light is still moving; the sensor stops when the app is hidden
//     and while power saving is on (state/power.svelte.ts).
//  2. A bloom from the touch point: a throwaway layer animated with opacity + transform (compositor only).
//  3. Real edge refraction where the engine supports SVG filters in backdrop-filter (Chromium: Telegram
//     Android and Desktop). WebKit ignores url() there, so iOS keeps the rim light only.
//  4. Jelly: squash-and-stretch of a sliding pill when it starts to move.
import { deviceOrientation, on, tg } from '../lib/tg';

/** Telegram Android appends the device performance class to the User-Agent; LOW turns power saving on (in Auto) */
export const LOW = /;\s*LOW\)/.test(navigator.userAgent);

const lit = new Set<HTMLElement>();
const light = { x: 0, y: 0, tx: 0, ty: 0, base: null as number | null, raf: 0, started: false, shown: '' };
const clamp = (v: number) => Math.max(-1, Math.min(1, v));

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
  sensor.stop = () => { light.base = null; try { d.stop(); } catch { /* already off */ } };
  on('deviceOrientationChanged', () => {
    if (d.beta == null || d.gamma == null) return; // radians
    // the way the phone is held at first is "neutral"; drifts slowly so a new posture becomes neutral too
    light.base = light.base == null ? d.beta : light.base + (d.beta - light.base) * 0.005;
    light.tx = clamp(d.gamma * 2.2);
    light.ty = clamp((d.beta - light.base) * 2.2);
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
 *  isn't moved by transform itself. */
export function jelly(el: HTMLElement | undefined): void {
  el?.animate?.([
    { transform: 'scale(1, 1)' },
    { transform: 'scale(1.16, 0.9)', offset: 0.35 },
    { transform: 'scale(0.97, 1.03)', offset: 0.7 },
    { transform: 'scale(1, 1)' },
  ], { duration: 480, easing: 'ease-out' });
}
