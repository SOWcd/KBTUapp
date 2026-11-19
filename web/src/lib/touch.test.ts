// A card's fetch ahead: a tap asks for it, a flick (the browser's pointercancel) never does, a mouse asks at once.
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AHEAD_MS, touchAhead } from './touch';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const down = (pointerType: string) => {
  const el = new EventTarget();
  const run = vi.fn();
  touchAhead({ pointerType, currentTarget: el } as unknown as PointerEvent, run);
  return { el, run };
};

it('a flick asks nothing', () => {
  const { el, run } = down('touch');
  vi.advanceTimersByTime(30);
  el.dispatchEvent(new Event('pointercancel'));  // the browser took the touch for a scroll
  vi.advanceTimersByTime(1000);
  el.dispatchEvent(new Event('pointerup'));
  expect(run).not.toHaveBeenCalled();
});

it('a quick tap asks once, as the finger lifts', () => {
  const { el, run } = down('touch');
  vi.advanceTimersByTime(40);
  el.dispatchEvent(new Event('pointerup'));
  expect(run).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(1000);
  el.dispatchEvent(new Event('pointercancel'));
  expect(run).toHaveBeenCalledTimes(1);
});

it('a held finger asks once, before it lifts', () => {
  const { el, run } = down('touch');
  vi.advanceTimersByTime(AHEAD_MS - 1);
  expect(run).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(run).toHaveBeenCalledTimes(1);
  el.dispatchEvent(new Event('pointerup'));
  expect(run).toHaveBeenCalledTimes(1);
});

it('a mouse asks at once, a pen waits as a finger does', () => {
  expect(down('mouse').run).toHaveBeenCalledTimes(1);
  expect(down('pen').run).not.toHaveBeenCalled();
});
