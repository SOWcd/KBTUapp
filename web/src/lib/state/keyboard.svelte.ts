// The on-screen keyboard as one number: how many pixels of the app's box it covers at the bottom (keyboard.h).
// The app's box (#app) keeps the height it had without a keyboard (--app-h): the webview shrinking under it (Telegram
// iOS resizes it 0.4 s after the keyboard came up, WebAppController; Android with it, in steps) relays out nothing, so
// nothing jumps. What sits at the bottom rides up by keyboard.h instead: a sheet (ui/Sheet) moves its panel or its
// footer with one tween timed like the keyboard; the scroller holding the field (a page, a pane) gets that much more
// room at its end. Nothing is set on the root while typing: a root attribute or variable restyled the whole app
// (~100 ms on a full tab, in the middle of the keyboard's rise).
// The covered part is read from window.visualViewport, which shrinks first on iOS (the keyboard over the webview) and
// together with the window on Android; one formula holds through both phases: the box's height minus the visible
// bottom. A hardware keyboard covers nothing: 0.
// iOS reports late: Telegram's frame change lands ~0.4 s after the keyboard started, when it is fully up, and the
// content then jumped into place under a keyboard that had slid over it. So on iOS a tap into a field starts the ride
// at once, towards the height the keyboard had last time (remembered per screen width); the real report then corrects
// it with a short glide, and no report within 0.8 s (a hardware keyboard) takes it back down. Android's webview
// resizes in step with its keyboard: no guess there.
import { onIos } from '../tg';

export const keyboard = $state({ h: 0 });

// what opens a keyboard (iOS's date and time fields open a popover, a readonly one nothing)
const EDIT = 'textarea:not([readonly], :disabled, [inputmode=none]), [contenteditable=""], [contenteditable="true"], input:not([type=checkbox], [type=radio], [type=range], [type=button], [type=submit], [type=reset], [type=image], [type=file], [type=color], [type=date], [type=time], [type=datetime-local], [type=month], [type=week], [readonly], :disabled, [inputmode=none])';
export const editing = () => !!(document.activeElement as Element | null)?.matches?.(EDIT);
/** the keyboard's own motion: iOS announces 0.25 s (UIKeyboardAnimationDurationUserInfoKey) on its private spring-like
 *  curve 7, here an ease-out a touch ahead of it (the field never under its edge); Android's inset animation */
export const KB_MS = onIos ? 250 : 220;
export const kbEase = (x: number) => (x >= 1 ? 1 : x <= 0 ? 0 : 1 - Math.pow(1 - x, 3.2));

let full = 0, wide = 0, settle = 0, still = 0, focusAt = 0;
// the guess: its height while no real report came yet; firm: the real reports stopped changing; tapAt: a keyboard comes
// only for a field focused by a tap (iOS); noKb: the last guess saw no keyboard (a hardware one): no more guessing
let guess = 0, guessT = 0, firm = 0, tapAt = -1e9, noKb = false;
const KEY = 'kb-h';
let learnt: Record<string, number> = {};
try { learnt = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch { /* blocked */ }
// first run: iPhone's keyboard with its suggestions bar, 336 pt on the 375-393 pt phones, 346 on the wide ones; a
// landscape phone or an iPad waits for one real report
const guessFor = () => learnt[innerWidth] ?? (innerWidth < 400 ? 336 : innerWidth < 500 ? 346 : 0);
function learn(h: number) {
  if (!onIos || h < 60 || learnt[innerWidth] === h) return;
  learnt[innerWidth] = h;
  try { localStorage.setItem(KEY, JSON.stringify(learnt)); } catch { /* blocked */ }
}
function predict() {
  const g = onIos && !noKb && performance.now() - tapAt < 1000 && editing() ? guessFor() : 0;
  if (!g) return;
  guess = g;
  clearTimeout(guessT);
  guessT = window.setTimeout(() => { if (guess) { guess = 0; noKb = true; apply(); } }, 800);
}
/** how long a rise may take to land with the keyboard: what is left of its motion since the field took the focus (a
 *  late report, Telegram iOS's resize 0.4 s on, finds it up already: a short glide, not a slow one) */
export const riseMs = () => Math.max(120, KB_MS - (performance.now() - focusAt));
const root = typeof document !== 'undefined' ? document.documentElement : null;

function apply() {
  const vv = window.visualViewport;
  // iOS pans the visual viewport to show a field the keyboard covers (the whole app slid up, then down): we place the
  // field ourselves, so the pan goes back
  if (vv && editing() && (vv.offsetTop > 0 || scrollY > 0)) scrollTo(0, 0);
  const bottom = vv ? vv.offsetTop + vv.height : innerHeight;
  // below 60 px it's no keyboard (a bar, a rounding); while no field has the focus it's none either (it is going down)
  let h = Math.max(0, Math.round(full - bottom));
  if (h < 60 || !editing()) h = 0;
  if (h) { noKb = false; clearTimeout(guessT); }
  if (!editing()) guess = 0;
  // the real one rising in parts never pulls the guess back down; once its reports stand, it alone
  else if (guess && h) { clearTimeout(firm); firm = window.setTimeout(() => { guess = 0; apply(); learn(keyboard.h); }, Math.max(150, focusAt + KB_MS + 150 - performance.now())); }
  h = Math.max(h, guess);
  if (h !== keyboard.h) {
    keyboard.h = h;
    pad(h);
    clearTimeout(still);
    if (h) still = window.setTimeout(() => { reveal(); if (!guess) learn(keyboard.h); }, KB_MS + 60); // once it stands
  }
}

function measure() {
  // a turn of the phone (or a desktop window's new width) starts over; the box grows at once, and shrinks only when
  // things are calm and nothing is being typed (a keyboard going down passes through every smaller height)
  if (innerWidth !== wide) { wide = innerWidth; full = innerHeight; }
  else if (innerHeight > full) full = innerHeight;
  clearTimeout(settle);
  settle = window.setTimeout(() => { if (!editing() && innerHeight !== full) { full = innerHeight; root!.style.setProperty('--app-h', `${full}px`); apply(); } }, 700);
  root!.style.setProperty('--app-h', `${full}px`);
  apply();
}

if (root && typeof window !== 'undefined') {
  measure();
  addEventListener('resize', measure);
  window.visualViewport?.addEventListener('resize', measure);
  window.visualViewport?.addEventListener('scroll', apply);
  // focus moving from field to field is one focusout then one focusin in the same task: look after both
  addEventListener('pointerdown', () => (tapAt = performance.now()), true);
  addEventListener('focusin', () => {
    if (!keyboard.h) { focusAt = performance.now(); predict(); }
    queueMicrotask(apply);
    if (keyboard.h) setTimeout(reveal, 60); // up already: the next field
  });
  addEventListener('focusout', () => queueMicrotask(apply));
}

// the room: a spacer at the end of the field's scroller (Sheet keeps its own: data-kb-own); one at a time
let spacer: HTMLElement | null = null;
const scrollerOf = (el: Element | null) => {
  let sc = el?.parentElement ?? null;
  while (sc && sc !== document.body && !/auto|scroll/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
  return sc === document.body ? null : sc;
};
function pad(h: number) {
  const sc = h ? scrollerOf(document.activeElement) : null;
  if (!sc || sc.hasAttribute('data-kb-own')) { spacer?.remove(); spacer = null; return; }
  if (spacer?.parentElement !== sc) { spacer?.remove(); spacer = document.createElement('div'); spacer.setAttribute('aria-hidden', 'true'); spacer.style.flex = 'none'; }
  spacer.style.height = `${h}px`;
  if (sc.lastElementChild !== spacer) sc.append(spacer);
}

/** the focused field, if the keyboard hides it (or a sheet's raised footer does), scrolled into the visible part of
 *  its scroller, smoothly; the browser's own reveal was what moved the whole page */
export function reveal() {
  const el = document.activeElement as HTMLElement | null;
  if (!el || !editing()) return;
  // a field in a sheet's body: above its raised footer too
  const foot = el.closest('.sheet')?.querySelector(':scope > .foot');
  const limit = foot && !foot.contains(el) ? foot.getBoundingClientRect().top : Infinity;
  const sc = scrollerOf(el);
  if (!sc) return;
  // the keyboard as we hold it (the guess included: the webview may not know of it yet)
  const bottom = Math.min(limit, full - keyboard.h) - 16;
  const r = el.getBoundingClientRect(), top = sc.getBoundingClientRect().top + 8;
  const by = r.bottom > bottom ? Math.min(r.bottom - bottom, r.top - top) : r.top < top ? r.top - top : 0;
  if (by) sc.scrollBy({ top: by, behavior: 'smooth' });
}
