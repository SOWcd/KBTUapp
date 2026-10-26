// Power saving (in Low Power Mode the app lagged on his iPhone; "it should notice, go light and say so").
// The light look is `html.lowfx`: no live blur anywhere (base.css), no tilt light (glass.ts), no endless motion (the
// Feed's slow zoom and floats, the legend medal's spin, shines and glows), no flights between screens (fly.ts), half
// the emoji in a burst, the theme switches without the circle; everything still works the same. Settings has Auto
// (the default), On and Off; in Auto it is on while any of these holds:
//  - the screen draws ~30 frames a second: iOS halves requestAnimationFrame and CSS animations in Low Power Mode and
//    when the phone is hot (WebKit's LowPowerMode and ThermalMitigation throttling); no API tells a page either;
//  - Telegram marks the phone LOW performance (Android's User-Agent);
//  - the battery is at 20% or less and not charging, where the browser tells (Chromium; iOS doesn't).
// The rate (frames.ts) is measured at idle a second after the start, again when the app comes back and every minute;
// a change must show twice in a row, 1.5 s apart. Inside a frame (Telegram Web) it waits for the first tap, as Safari
// caps a cross-origin frame until one. The verdict is kept, so a phone in Low Power Mode opens light at once.
// Turning on by itself says so (a toast), once until it has been off again.
import { LOW, tilt } from '../../ui/glass';
import { capped, rateOf, type Rate } from '../frames';
import { t } from '../i18n/index.svelte';
import { on } from '../tg';
import { say } from './ui.svelte';

export type PowerMode = 'auto' | 'on' | 'off';
export const POWER_MODES: PowerMode[] = ['auto', 'on', 'off'];
const KEY = 'kb-power';

const kept = (() => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') ?? {}; } catch { return {}; } })();
export const power = $state({
  mode: (POWER_MODES.includes(kept.mode) ? kept.mode : 'auto') as PowerMode,
  lite: false,
  why: null as 'fps' | 'battery' | 'device' | null, // in Auto, why it's on
  fps: 0,                                           // the last rate that told something, to tens; 0 = not yet
});
let slow = kept.slow === true, told = kept.told === true, battery = false;
const keep = () => { try { localStorage.setItem(KEY, JSON.stringify({ mode: power.mode, slow, told })); } catch { /* blocked */ } };
const root = document.documentElement;

function apply(): void {
  power.why = power.mode !== 'auto' ? null : slow ? 'fps' : battery ? 'battery' : LOW ? 'device' : null;
  const lite = power.mode === 'on' || !!power.why;
  if (lite === root.classList.contains('lowfx')) return;
  power.lite = lite;
  root.classList.toggle('lowfx', lite);
  tilt(!lite);
  if (power.mode !== 'auto' || lite === told) return;
  told = lite;
  keep();
  // after the first screen has shown, if it's the start
  if (lite) setTimeout(() => say(t(power.why === 'device' ? 'power.sayDevice' : 'power.say'), 'high_voltage_3d'), Math.max(0, 2500 - performance.now()));
}

/** The rate of 24 idle frames, or null when none came for 2.5 s (hidden). */
function measure(): Promise<Rate> {
  return new Promise((done) => {
    const at: number[] = [];
    let over = false;
    const end = (r: Rate) => { if (!over) { over = true; done(r); } };
    setTimeout(() => end(null), 2500);
    const frame = (ts: number) => {
      if (over) return;
      at.push(ts);
      if (at.length > 24) end(rateOf(at.slice(1).map((x, i) => x - at[i])));
      else requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
}

let ready = false, busy = false;
async function check(): Promise<void> {
  if (!ready || busy || document.hidden || power.mode !== 'auto') return;
  busy = true;
  try {
    let r = await measure();
    const v = capped(r);
    if (v != null && v !== slow) { // a change: it must show again
      await new Promise((ok) => setTimeout(ok, 1500));
      r = await measure();
      if (capped(r) === v) { slow = v; keep(); apply(); }
    }
    if (capped(r) != null) power.fps = Math.round(r!.fps / 10) * 10;
  } finally { busy = false; }
}

/** The person's pick in Settings. */
export function setPowerMode(mode: PowerMode): void {
  power.mode = mode;
  keep();
  apply();
  setTimeout(check, 400);
}

const framed = (() => { try { return window.self !== window.top; } catch { return true; } })();
const start = () => { ready = true; setTimeout(check, 1000); };
if (framed) addEventListener('click', start, { capture: true, once: true }); else setTimeout(start, 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) setTimeout(check, 1000); });
on('activated', () => setTimeout(check, 1000));
setInterval(check, 60_000);

type Battery = EventTarget & { level: number; charging: boolean };
(navigator as Navigator & { getBattery?: () => Promise<Battery> }).getBattery?.().then((b) => {
  const read = () => { battery = !b.charging && b.level <= 0.2; apply(); };
  b.addEventListener('levelchange', read);
  b.addEventListener('chargingchange', read);
  read();
}).catch(() => { /* not allowed here */ });

apply(); // before the first paint (main.ts imports this first)
