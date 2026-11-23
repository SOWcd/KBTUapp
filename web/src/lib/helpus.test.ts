import { describe, expect, it } from 'vitest';
import { engaged, withDay } from './helpus';

describe('the help ask: who is engaged', () => {
  it('five different days of the last fourteen, a week after the first', () => {
    let k = null as ReturnType<typeof withDay> | null;
    for (const d of [100, 100, 101, 103, 104]) k = withDay(k, d);
    expect(k).toEqual({ f: 100, d: [100, 101, 103, 104] });
    expect(engaged(k, 104)).toBe(false);          // four days
    k = withDay(k, 106);
    expect(engaged(k, 106)).toBe(false);          // five days, but here for six
    k = withDay(k, 107);
    expect(engaged(k, 107)).toBe(true);
    expect(engaged(withDay(k, 125), 125)).toBe(false); // back after a long break: one day in the window
    expect(withDay(k, 125)).toEqual({ f: 100, d: [125] });
    expect(engaged(null, 107)).toBe(false);
  });
});
