// The boot screen of index.html (#boot: the lights and the mark, painted before the bundle), handed over to the page.
const el = () => document.getElementById('boot');
const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const CYCLE = 2600, DELAY = 350; // its glint's loop (index.html kb-glint)

/** over everything again, its mark in the middle: a session check under way */
export const bootOver = (): void => el()?.classList.remove('u');

/** Under the page from now on, as its ground of lights, with its mark hidden: the page draws its own (.kb-mark) instead.
 *  Returns where the boot's mark stood and how far its glint had got, for the page's mark to carry on from; null when
 *  there is nothing to carry on (no boot screen, already under, less motion asked for). */
export function bootUnder(): { x: number; y: number; glint: number } | null {
  const b = el(), m = b?.querySelector('.kb-mark');
  if (!b || !m || b.classList.contains('u')) return null;
  const r = m.getBoundingClientRect(), t = Number(m.querySelector('i')?.getAnimations()[0]?.currentTime ?? 0);
  b.classList.add('u');
  return still() || !r.width ? null : { x: r.x, y: r.y, glint: t < DELAY ? t : DELAY + ((t - DELAY) % CYCLE) };
}

/** gone: faded away over the app (a signed-in launch), or at once when the app already covers it */
export function bootOut(): void {
  const b = el();
  if (!b) return;
  if (b.classList.contains('u') || still() || !b.offsetWidth) return b.remove();
  b.classList.add('o');
  setTimeout(() => b.remove(), 460);
}
