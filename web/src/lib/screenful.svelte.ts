// Long lists of people open in the tap's frame: a screenful of rows is drawn at once, the rest join after the first
// paint, a frame's worth at a time (2000 guests drawn in one go held the main thread 1-3 s at 4x CPU, issue 339).
// (content-visibility on the rows was tried first: it made each scroll frame slower at 4x CPU.) A list needs one line:
//   const draw = screenful(() => rows.length);  +  {#each rows.slice(0, draw.n) as r (r.id)}
// Tall cards (News's posts, 200-400 px) pass how many fill a screen: screenful(() => n, 5), and the batches start at one.
import { flushSync } from 'svelte';

const FIRST = 30;   // rows drawn with the sheet: more than a tall phone shows (rows are 44-60 px)
const BUDGET = 10;  // ms of drawing per frame after it, so a scroll or a tap meanwhile still answers in its frame

/** How many of a list's rows to draw now: FIRST at once, then more after each painted frame until all of them. It
 *  never shrinks, so a search or a new order redraws only what is drawn and the scroll position stays. */
export function screenful(total: () => number, first = FIRST): { readonly n: number } {
  let n = $state(first), step = first < FIRST ? 1 : 20; // the first batch's guess; each batch sizes the next to BUDGET
  $effect(() => {
    if (n >= total()) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // the timer after the frame's callback runs once that frame is painted
    const frame = requestAnimationFrame(() => (timer = setTimeout(() => {
      const t0 = performance.now();
      flushSync(() => (n += step));
      step = Math.min(500, Math.max(5, Math.round(step * BUDGET / Math.max(1, performance.now() - t0))));
    })));
    return () => { cancelAnimationFrame(frame); clearTimeout(timer); };
  });
  return { get n() { return n; } };
}
