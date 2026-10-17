// A 30 fps cap is told from 60 and 120 by steady frames; fast frames mean no cap however uneven; a busy, uneven,
// slow run tells nothing.
import { expect, it } from 'vitest';
import { capped, rateOf } from './frames';

const run = (ms: number, n = 24) => Array.from({ length: n }, (_, i) => ms + (i % 3) * 0.4 - 0.4); // a little jitter

it('tells a capped screen from a free one', () => {
  expect(capped(rateOf(run(33.3)))).toBe(true);                       // Low Power Mode or a hot iPhone
  expect(Math.round(rateOf(run(33.3))!.fps)).toBe(30);
  expect(capped(rateOf(run(16.7)))).toBe(false);                      // 60 Hz (Safari on a 120 Hz iPhone too)
  expect(capped(rateOf(run(8.3)))).toBe(false);                       // 120 Hz
  expect(capped(rateOf([...run(8.3, 14), ...run(16.7, 10)]))).toBe(false); // 120 Hz that drops frames: uneven, still free
  expect(capped(rateOf([...run(16.7, 18), 50, 120, 70, 90, 300]))).toBe(false); // a few long frames don't make a cap
  expect(capped(rateOf([16.7, 50, 33, 66, 16.7, 100, 33, 50, 16.7, 83, 33, 50]))).toBe(null); // busy: slow but uneven
  expect(rateOf(run(33.3, 5))).toBe(null);                            // too few to tell
  expect(capped(rateOf(run(22)))).toBe(null);                         // 45 fps: neither
});
