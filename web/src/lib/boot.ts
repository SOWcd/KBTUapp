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

/** gone: the view flies in through its colonnade and it dissolves over the app (a signed-in launch; index.html's .o, under half a second, whatever the intro
 *  was doing: the app never waits for it), or at once when the app already covers it */
export function bootOut(): void {
  const b = el();
  if (!b) return;
  const gone = () => { b.remove(); delete document.documentElement.dataset.boot; }; // (its ground on <html> goes with it: the theme's own from here)
  if (b.classList.contains('u') || still() || !b.offsetWidth) return gone();
  b.classList.add('o');
  setTimeout(gone, 520);
}
