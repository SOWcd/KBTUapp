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
import { onIos } from '../tg';

export const keyboard = $state({ h: 0 });

const EDIT = 'textarea, [contenteditable=""], [contenteditable="true"], input:not([type=checkbox], [type=radio], [type=range], [type=button], [type=submit], [type=file], [type=color])';
export const editing = () => !!(document.activeElement as Element | null)?.matches?.(EDIT);
/** the keyboard's own motion: iOS ~0.25-0.35 s on its spring, approximated; Android's inset animation is shorter */
export const KB_MS = onIos ? 300 : 220;
export const kbEase = (x: number) => (x >= 1 ? 1 : x <= 0 ? 0 : 1 - Math.pow(1 - x, 3.2));

let full = 0, wide = 0, settle = 0, still = 0, focusAt = 0;
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
  if (h !== keyboard.h) {
    keyboard.h = h;
    pad(h);
    clearTimeout(still);
    if (h) still = window.setTimeout(reveal, KB_MS + 60); // once it stands
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
  addEventListener('focusin', () => { if (!keyboard.h) focusAt = performance.now(); queueMicrotask(apply); if (keyboard.h) setTimeout(reveal, 60); }); // up already: the next field
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
  const vv = window.visualViewport, bottom = Math.min(limit, vv ? vv.offsetTop + vv.height : innerHeight) - 16;
  const r = el.getBoundingClientRect(), top = sc.getBoundingClientRect().top + 8;
  const by = r.bottom > bottom ? Math.min(r.bottom - bottom, r.top - top) : r.top < top ? r.top - top : 0;
  if (by) sc.scrollBy({ top: by, behavior: 'smooth' });
}
