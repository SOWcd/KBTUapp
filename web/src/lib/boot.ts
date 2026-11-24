// The boot screen of index.html (#boot: the emblem on the plain ground, painted before the bundle), handed over to the page.
const el = () => document.getElementById('boot');
const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/** over everything again, its emblem in the middle: a session check under way */
export const bootOver = (): void => el()?.classList.remove('u');

/** Under the page from now on, as its ground: the lights wake, the legend goes, the emblem's mark is hidden: the page
 *  draws its own in its place. Returns where that mark stood, for the page's to start from; null when there is nothing
 *  to carry on (no boot screen, already under, less motion asked for). */
export function bootUnder(): DOMRect | null {
  const b = el(), m = b?.querySelector('.mk');
  if (!b || !m || b.classList.contains('u')) return null;
  const from = m.getBoundingClientRect();
  b.classList.add('u');
  return still() || !from.width ? null : from;
}

/** gone: its emblem settles back and dissolves as the app lifts in under it (a signed-in launch; index.html's .o, 0.3 s,
 *  whatever the intro was doing), or at once when the app already covers it. An app ready sooner than 0.4 s after the
 *  first paint waits until then (owner, Nov 22: the intro is seen), never longer. */
export function bootOut(): void {
  const b = el();
  if (!b) return;
  const gone = () => { b.remove(); delete document.documentElement.dataset.boot; }; // (its ground on <html> goes with it: the theme's own from here)
  if (b.classList.contains('u') || still() || !b.offsetWidth) return gone();
  const out = () => { b.classList.add('o'); setTimeout(gone, 340); };
  // the legend's animation began with the first paint: its clock is the time since (none once it has ended, 0.6 s)
  const t = Number(b.querySelector('.lg')?.getAnimations?.()[0]?.currentTime ?? NaN);
  if (t >= 0 && t < 400) setTimeout(out, 400 - t); else out();
}
