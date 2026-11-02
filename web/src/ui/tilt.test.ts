import { describe, expect, it } from 'vitest';
import { springStep, tiltFrom, upOf } from './tilt';

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

describe('the medal swings by time, not by frames', () => {
  const after = (hz: number, ms: number, k = 60 / hz) => { const p = { x: 4, v: 0 }; for (let t = 0; t < ms; t += 1000 / hz) springStep(p, 0, k); return p.x; };
  it('one step at 60 Hz is the old per-frame step', () => {
    const p = { x: 4, v: 0 };
    springStep(p, 0, 1);
    expect(p.v).toBeCloseTo((0 + (0 - 4) * 0.045) * 0.92, 12);
    expect(p.x).toBeCloseTo(4 + p.v, 12);
  });
  it('120 Hz and 30 Hz screens follow the 60 Hz swing, far closer than stepping per frame did', () => {
    for (const ms of [150, 400, 900]) {
      expect(Math.abs(after(120, ms) - after(60, ms))).toBeLessThan(0.2); // of a 4 degree swing
      for (const hz of [120, 30]) expect(Math.abs(after(hz, ms) - after(60, ms))).toBeLessThan(Math.abs(after(hz, ms, 1) - after(60, ms)));
    }
  });
});
