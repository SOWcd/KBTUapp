import { haptic } from '../lib/tg';

/** {@attach longPress(fn)}: a held press (Android's long press, a computer's right click) runs fn instead of the tap. A
 *  finger that moves or a scroll (the browser's pointercancel) calls it off. */
export const longPress = (fire: (el: HTMLElement) => void, ms = 450) => (el: HTMLElement) => {
  let timer = 0, x = 0, y = 0, held = false;
  const stop = () => clearTimeout(timer);
  // the click iOS still sends on release lands on whatever fire() put under the finger: the next one is eaten, wherever
  const eat = (e: Event) => { e.stopPropagation(); e.preventDefault(); off(); };
  const off = () => { removeEventListener('click', eat, true); removeEventListener('pointerdown', off, true); };
  const go = () => { held = true; haptic.rigid(); fire(el); addEventListener('click', eat, true); addEventListener('pointerdown', off, true); };
  const down = (e: PointerEvent) => { held = false; if (e.button) return; x = e.clientX; y = e.clientY; timer = window.setTimeout(go, ms); };
  const move = (e: PointerEvent) => { if (Math.hypot(e.clientX - x, e.clientY - y) > 10) stop(); };
  const context = (e: Event) => { e.preventDefault(); stop(); if (!held) go(); };
  const ends = ['pointerup', 'pointercancel'];
  el.addEventListener('pointerdown', down);
  el.addEventListener('pointermove', move);
  el.addEventListener('contextmenu', context);
  ends.forEach((n) => el.addEventListener(n, stop));
  return () => {
    stop(); off();
    el.removeEventListener('pointerdown', down);
    el.removeEventListener('pointermove', move);
    el.removeEventListener('contextmenu', context);
    ends.forEach((n) => el.removeEventListener(n, stop));
  };
};
