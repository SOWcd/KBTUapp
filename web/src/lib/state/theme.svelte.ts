// Theme: the person's choice (light / dark) or, by default, Telegram's own scheme.
// Switching sets one attribute on <html>; tokens.css does the rest. Rare, so the whole-document
// restyle is fine (the prototype's lag came from CSS vars changed every frame, not from this).
// The switch flows (owner, Oct 4): a view transition grows the new theme as a circle from the tapped button, the way
// Telegram's own night-mode switch does, or fades it in when Telegram changes the scheme on its own.
import { flushSync } from 'svelte';
import { paint, on, tg } from '../tg';

export type Theme = 'light' | 'dark';
const KEY = 'kb-theme';

export const theme = $state({ current: 'dark' as Theme, chosen: null as Theme | null });

export function initialTheme(telegram: Theme): Theme {
  let chosen: Theme | null = null;
  try { const v = localStorage.getItem(KEY); if (v === 'light' || v === 'dark') chosen = v; } catch { /* blocked */ }
  theme.chosen = chosen;
  // follow Telegram live while the person hasn't picked one
  on('themeChanged', () => { if (!theme.chosen) flow(tg.colorScheme()); });
  return chosen ?? telegram;
}

export function applyTheme(t: Theme, telegramToo = true): void {
  theme.current = t;
  document.documentElement.dataset.theme = t;
  if (telegramToo) paintFor(t);
}

/** Telegram's own surfaces (background, header, bottom bar) in a theme's colour */
export const paintFor = (t: Theme) => paint(t === 'light' ? '#F3F5FB' : '#07080F');

const webkit = /AppleWebKit/.test(navigator.userAgent) && !/Chrome|Android/.test(navigator.userAgent); // iPhone, Mac Safari
let running: ViewTransition | null = null; // a second tap mid-way starts over; only the latest one tidies up

// cubic-bezier(.3, 0, .2, 1), the circle's easing: the share of its duration it takes to reach progress p
const curve = (a: number, b: number, s: number) => 3 * a * s * (1 - s) ** 2 + 3 * b * s * s * (1 - s) + s ** 3;
function timeAt(p: number): number {
  let lo = 0, hi = 1;
  for (let i = 0; i < 24; i++) { const s = (lo + hi) / 2; if (curve(0, 1, s) < p) lo = s; else hi = s; }
  return curve(0.3, 0.2, (lo + hi) / 2);
}

/** `change` (a new look) under a view transition: a circle growing from `from` (the tapped button), or a fade without
 *  one; `done` (Telegram's own surfaces: its buttons over the top) as the circle passes the top of the screen, or once
 *  the fade is over. Instant where the webview has no view transitions (iOS before 18, old Android webviews), the
 *  person asked for less motion, or power saving is on. The map's own theme switch uses it too.
 *  The new look's glass is solid while the transition runs (`vt-solid`, base.css): its live snapshot can't draw what's
 *  behind glass (iOS), so the old look's glass showed through and snapped over at the end (owner, Oct 6); once it's
 *  over the glass clears up in a third of a second. `look: 'lang'`: a new language's words come into focus over the
 *  old ones (base.css .vt-lang; owner, Oct 24: "the language switch must be beautiful"). */
export function reveal(change: () => void, done: () => void, from?: Element, look?: 'lang'): void {
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('lowfx')) { change(); return done(); }
  const root = document.documentElement;
  const b = from?.getBoundingClientRect(), at = b && { x: b.left + b.width / 2, y: b.top + b.height / 2 };
  root.classList.toggle('vt-circle', !!at);
  root.classList.toggle('vt-lang', look === 'lang');
  // WebKit's OLD snapshot drops backdrop-filter too: the bars turned clear at the tap, the page sharp through them, long
  // before the circle came (owner's video, Oct 25). Solid glass looks the same as blurred glass at a glance, so there
  // it goes solid before the old look is captured
  if (webkit) root.classList.add('vt-solid');
  const vt = (running = document.startViewTransition(() => { root.classList.add('vt-solid'); flushSync(change); }));
  let painted = false;
  const paint = () => { if (!painted && running === vt) { painted = true; done(); } };
  if (at) vt.ready.then(() => {
    const r = Math.hypot(Math.max(at.x, innerWidth - at.x), Math.max(at.y, innerHeight - at.y));
    root.animate({ clipPath: [`circle(0 at ${at.x}px ${at.y}px)`, `circle(${r}px at ${at.x}px ${at.y}px)`] },
      { duration: 480, easing: 'cubic-bezier(0.3, 0, 0.2, 1)', pseudoElement: '::view-transition-new(root)' });
    setTimeout(paint, 480 * timeAt(Math.min(1, Math.hypot(at.x - innerWidth / 2, at.y) / r))); // the top centre, where Telegram's buttons are
  }).catch(() => {});
  const tidy = () => { paint(); if (running === vt) { running = null; root.classList.remove('vt-circle', 'vt-lang', 'vt-solid'); } };
  vt.finished.then(tidy, tidy);
}

/** Telegram's surfaces (its buttons over the top, the status bar's tint) turn as the circle reaches the top, so the
 *  top changes with the rest of it (owner, Oct 6: they used to snap over after the circle). */
function flow(t: Theme, from?: Element): void {
  if (t !== theme.current) reveal(() => applyTheme(t, false), () => applyTheme(theme.current), from);
}

/** The person's pick; `from` is the tapped button, where the new theme starts to grow. */
export function chooseTheme(t: Theme, from?: Element): void {
  theme.chosen = t;
  try { localStorage.setItem(KEY, t); } catch { /* blocked */ }
  flow(t, from);
}
