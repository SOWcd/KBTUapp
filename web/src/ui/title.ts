// Large titles (a tab screen's, a pushed page's): they fit their line, and the capsule takes over once they scroll away.
import { ui, type Tab } from '../lib/state/ui.svelte';

/** A large title (34) wraps between words and never inside one: when its longest word doesn't fit the line
 *  (the Russian "Privacy" at 320 px), the whole title shrinks until it does, down to `min` (24); a word still too long
 *  then breaks at its soft hyphen (the dictionaries put one in every word of 15+ letters), never anywhere.
 *  `use:fitTitle` on every large title; it measures again when the text or the width changes. */
export function fitTitle(el: HTMLElement, min = 24): { destroy: () => void } {
  let busy = false;
  const run = () => {
    if (busy) return;
    busy = true;
    const s = el.style;
    s.fontSize = '';
    // measure the words whole: no break inside one, not even at a soft hyphen (shrinking comes first)
    s.overflowWrap = 'normal'; s.hyphens = 'none'; s.setProperty('-webkit-hyphens', 'none');
    const max = parseFloat(getComputedStyle(el).fontSize);
    if (el.scrollWidth > el.clientWidth + 1) s.fontSize = `${Math.max(Math.min(min, max), Math.floor((max * el.clientWidth) / el.scrollWidth))}px`;
    s.overflowWrap = ''; s.hyphens = ''; s.removeProperty('-webkit-hyphens');
    busy = false;
  };
  const ro = new ResizeObserver(run);
  ro.observe(el);
  const mo = new MutationObserver(run);
  mo.observe(el, { childList: true, characterData: true, subtree: true });
  document.fonts?.ready.then(run); // the first measure may be in the fallback font
  return { destroy: () => { ro.disconnect(); mo.disconnect(); } };
}

/** `use:largeTitle={'afisha'}` on a tab screen's title, or `use:largeTitle={(gone) => …}`: says when the title has
 *  scrolled up under the capsule (the capsule then shows the screen's name, iOS's inline title) and when it's back. */
export function largeTitle(el: HTMLElement, to: Tab | ((gone: boolean) => void)): { destroy: () => void } {
  const say = (gone: boolean) => { if (typeof to === 'function') to(gone); else if (!!ui.gone[to] !== gone) ui.gone[to] = gone; };
  const top = document.querySelector('.cap.glass')?.getBoundingClientRect().bottom ?? 46; // the capsule's lower edge
  // a view out of the layout (display: none, My club vs All clubs) measures nothing: it says nothing either
  const io = new IntersectionObserver(([e]) => { if (e.boundingClientRect.height) say(!e.isIntersecting && e.boundingClientRect.top < top); },
    { rootMargin: `-${Math.round(top)}px 0px 0px 0px` });
  io.observe(el);
  return { destroy: () => { io.disconnect(); say(false); } };
}
