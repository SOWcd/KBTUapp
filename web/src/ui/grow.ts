/** A textarea as tall as what's typed (up to `max` px, then it scrolls): `use:grow` or `use:grow={132}`. */
export function grow(el: HTMLTextAreaElement, max = Infinity): void {
  const fit = () => { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, max) + 'px'; };
  fit();
  el.addEventListener('input', fit);
}
