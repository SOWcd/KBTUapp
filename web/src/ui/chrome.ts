// The Feed is always dark photos, so over it the nav and the capsule turn into dark glass tinted with the
// slide on screen. The blend follows the finger: the pager reports its position ('kb:pager') and two
// layers per element cross-fade (opacity, compositor only); the icon palette flips at the halfway point.
// Nothing here touches <html>: a variable there restyles the whole document on every frame.
type Part = { node: HTMLElement; base: HTMLElement; feed: HTMLElement };
const parts = new Set<Part>();
const state = { k: 0, rgb: '' };

function apply(p: Part, ease: string) {
  // the pager's ease is written for transform; the same curve and duration drive the cross-fade
  const tr = `${ease ? ease.replace(/transform/g, 'opacity') : 'opacity 0s'}, background-color 500ms ease`;
  p.base.style.transition = tr;
  p.feed.style.transition = tr;
  p.base.style.opacity = String(1 - state.k);
  p.feed.style.opacity = String(state.k);
  p.node.toggleAttribute('data-feed', state.k >= 0.5);
}

/** k = 0 normal chrome … 1 feed chrome. `ease` is a CSS transition for the move (empty = follow at once). */
export function feedChrome(k: number, ease = ''): void {
  state.k = Math.max(0, Math.min(1, k));
  for (const p of parts) apply(p, ease);
  for (const f of fades) fadeOut(f, ease);
}

// the fades under the capsule and the nav go away over the Feed, with the same blend (they used to vanish at
// the end of the swipe: the owner's video, Oct 21)
const fades = new Set<HTMLElement>();
function fadeOut(f: HTMLElement, ease: string) {
  f.style.transition = ease ? ease.replace(/transform/g, 'opacity') : 'none';
  f.style.opacity = String(1 - state.k);
}
export function unfeed(node: HTMLElement) {
  fades.add(node);
  fadeOut(node, '');
  return { destroy() { fades.delete(node); } };
}

/** Tint of the slide on screen, 'r g b'. */
export function feedTint(rgb: string): void {
  state.rgb = rgb;
  for (const p of parts) p.feed.style.setProperty('--feed-rgb', rgb);
}

/** Svelte action for the nav and the capsule; their children .tone-base and .tone-feed are the two layers. */
export function chrome(node: HTMLElement) {
  const base = node.querySelector<HTMLElement>(':scope > .tone-base');
  const feed = node.querySelector<HTMLElement>(':scope > .tone-feed');
  if (!base || !feed) return;
  const p = { node, base, feed };
  parts.add(p);
  if (state.rgb) feed.style.setProperty('--feed-rgb', state.rgb);
  apply(p, '');
  return { destroy() { parts.delete(p); } };
}
