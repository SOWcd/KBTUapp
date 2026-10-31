import { describe, expect, it, vi } from 'vitest';
import { queue } from './moments';

describe('moment queue', () => {
  it('opens one at a time, only on a free screen, a beat apart', async () => {
    vi.useFakeTimers();
    const open: string[] = [];
    const shown: string[] = [];
    const moment = queue(() => open.length > 0);
    moment(() => { shown.push('a'); open.push('a'); });
    moment(() => { shown.push('b'); open.push('b'); });
    await vi.advanceTimersByTimeAsync(600);
    expect(shown).toEqual(['a']);
    await vi.advanceTimersByTimeAsync(5000); // 'a' still open: 'b' waits
    expect(shown).toEqual(['a']);
    open.pop();
    await vi.advanceTimersByTimeAsync(1400);
    expect(shown).toEqual(['a', 'b']);
    vi.useRealTimers();
  });

  it('waits for a moment that is still opening', async () => {
    vi.useFakeTimers();
    let open = false;
    const shown: string[] = [];
    const moment = queue(() => open);
    moment(() => new Promise<void>((done) => setTimeout(() => { shown.push('slow'); open = true; done(); }, 2000)));
    moment(() => { shown.push('next'); });
    await vi.advanceTimersByTimeAsync(2700);
    expect(shown).toEqual(['slow']);
    open = false;
    await vi.advanceTimersByTimeAsync(1500);
    expect(shown).toEqual(['slow', 'next']);
    vi.useRealTimers();
  });
});
