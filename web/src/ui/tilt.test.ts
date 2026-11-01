import { describe, expect, it } from 'vitest';
import { tiltFrom, upOf } from './tilt';

describe('tilt is relative to how the phone is held', () => {
  it('a steady pose reads as face on, lying on the side included', () => {
    for (const [b, g] of [[0.7, 0], [0, 1.5], [0.2, -1.4], [1.5, 0.3]]) {
      const [x, y] = tiltFrom(upOf(b, g), upOf(b, g), 0);
      expect(Math.abs(x) + Math.abs(y)).toBeLessThan(1e-9);
    }
  });
  it('a turn from neutral tilts as much as the old gamma/beta did', () => {
    expect(tiltFrom(upOf(0, 0), upOf(0, 0.1), 0)[0]).toBeCloseTo(0.1 * 2.2, 1);
    expect(tiltFrom(upOf(0.1, 0), upOf(0.3, 0), 0)[1]).toBeCloseTo(0.2 * 2.2, 1);
    // on one's side: a small nod moves it a little, not a full turn
    const [x, y] = tiltFrom(upOf(0, 1.5), upOf(0.1, 1.5), 0);
    expect(Math.hypot(x, y)).toBeLessThan(0.3);
  });
  it('a landscape screen swaps the axes', () => {
    const [x, y] = tiltFrom(upOf(0, 0), upOf(0, 0.1), 90);
    expect(Math.abs(x)).toBeLessThan(0.01);
    expect(Math.abs(y)).toBeGreaterThan(0.15);
  });
});
