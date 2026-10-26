// The tapped poster grows into the event sheet's header (App Store style). A copy of the header starts on the poster,
// scaled down and clipped to the poster's shape around the cover's focus, and opens up into place on the sheet's own
// curve and time, so the two land together; the real header shows when it lands. Only where motion is welcome (not
// lowfx, not "reduce motion"), only from a poster on screen; otherwise the sheet just rises as before.
// Returns stop(): the copy goes at once (the sheet closing mid-flight).
export function fly(from: Element | null | undefined, to: HTMLElement, focus?: [number, number] | null): () => void {
  const panel = to.closest<HTMLElement>('[role=dialog]');
  if (!panel || !from?.isConnected || !Element.prototype.animate || document.documentElement.classList.contains('lowfx')
    || matchMedia('(prefers-reduced-motion: reduce)').matches) return () => {};
  const a = from.getBoundingClientRect();
  if (!a.width || a.bottom < 0 || a.top > innerHeight) return () => {};
  const [fx, fy] = focus ?? [0.5, 0.5];
  const r0 = parseFloat(getComputedStyle(from).borderTopLeftRadius) || 0;
  const r1 = parseFloat(getComputedStyle(to).borderTopLeftRadius) || 0;
  const copy = to.cloneNode(true) as HTMLElement;
  let anim: Animation | null = null;

  // where the header rests: the sheet's rise has only begun, so take its current lift off
  const aim = () => {
    const tf = getComputedStyle(panel).transform;
    const lift = (tf === 'none' ? 0 : new DOMMatrix(tf).m42) + (parseFloat(getComputedStyle(panel).translate.split(' ')[1]) || 0); // + a growing sheet's glide (Sheet)
    const b = to.getBoundingClientRect(), W = b.width, H = b.height, top = b.top - lift;
    // the poster's shape inside the header: same aspect, as large as fits, placed by the focus
    const sw = a.width / a.height < W / H ? H * a.width / a.height : W, sh = sw * a.height / a.width;
    const L = (W - sw) * fx, T = (H - sh) * fy, k = a.width / sw;
    Object.assign(copy.style, { left: b.left + 'px', top: top + 'px', width: W + 'px', height: H + 'px' });
    return [
      { transform: `translate(${a.left - b.left - k * L}px, ${a.top - top - k * T}px) scale(${k})`,
        clipPath: `inset(${T}px ${W - sw - L}px ${H - sh - T}px ${L}px round ${r0 / k}px)` },
      { transform: 'translate(0px, 0px) scale(1)', clipPath: `inset(0px 0px 0px 0px round ${r1}px)` },
    ];
  };
  Object.assign(copy.style, { position: 'fixed', margin: '0', zIndex: '55', pointerEvents: 'none', transformOrigin: '0 0' });
  copy.setAttribute('aria-hidden', 'true');
  const frames = aim();
  document.body.append(copy);
  // the poster itself leaves the list (back in place under the sheet once it lands); the header lands
  const src = from as HTMLElement;
  src.style.visibility = to.style.visibility = 'hidden';
  // the details arrive mid-flight and the sheet grows taller: aim again, so the copy still lands on the header
  const ro = new ResizeObserver(() => anim?.effect instanceof KeyframeEffect && anim.effect.setKeyframes(aim()));
  ro.observe(panel);
  const stop = () => { ro.disconnect(); anim?.cancel(); copy.remove(); src.style.visibility = to.style.visibility = ''; };
  const root = getComputedStyle(document.documentElement), t = root.getPropertyValue('--t-slow').trim();
  const ease = root.getPropertyValue('--ease-spring').trim() || 'ease-out';
  const ms = (parseFloat(t) || 0.38) * (t.endsWith('ms') ? 1 : 1000);   // the browser may hand it back in seconds
  anim = copy.animate(frames, { duration: ms, easing: ease, fill: 'both' });
  // the header's chips were not on the small poster: they come in on the way
  copy.querySelectorAll(':scope > :not(.poster)').forEach((c) => c.animate([{ opacity: 0 }, { opacity: 0, offset: 0.3 }, { opacity: 1 }], { duration: ms }));
  anim.onfinish = stop;
  return stop;
}
