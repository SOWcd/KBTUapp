// The one way a block opens or closes in place: `transition:fold` on the {#if} block (owner, Oct 13: a block that
// just appears looks cheap). Instant under lowfx and "reduce motion", like the rest of the motion.
import { slide } from 'svelte/transition';
import { cubicOut } from 'svelte/easing';

const calm = () => document.documentElement.classList.contains('lowfx') || matchMedia('(prefers-reduced-motion: reduce)').matches;

export function fold(node: Element, _?: unknown, opts?: { direction?: 'in' | 'out' | 'both' }) {
  if (calm()) return { duration: 0 };
  return slide(node, { duration: opts?.direction === 'out' ? 200 : 300, easing: cubicOut });
}
