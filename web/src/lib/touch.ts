// A fetch ahead from a touch, but not from a scroll. Was: a card's onpointerdown asked the server at once, and pointerdown
// fires for every finger that lands, so a flick over the Afisha or the forum asked for the details of each card it
// started on. Now a finger starts the fetch 80 ms into the touch, or at once when it lifts sooner (a tap), and a touch
// the browser takes over for a scroll (pointercancel, a flick's first ~30 ms) asks nothing. A tap's sheet still opens
// with the data on the way: a tap lasts ~100 ms, the fetch starts before the finger lifts. A mouse: at once, as before
// (no scroll starts from it); a pen scrolls like a finger.
export const AHEAD_MS = 80;

export function touchAhead(ev: PointerEvent, run: () => void): void {
  const el = ev.currentTarget as EventTarget | null;
  if (ev.pointerType === 'mouse' || !el) { run(); return; }
  let timer: ReturnType<typeof setTimeout>;
  const done = (go: boolean) => {
    clearTimeout(timer);
    el.removeEventListener('pointerup', up);
    el.removeEventListener('pointercancel', cancel);
    if (go) run();
  };
  const up = () => done(true);
  const cancel = () => done(false);
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', cancel);
  timer = setTimeout(() => done(true), AHEAD_MS);
}
