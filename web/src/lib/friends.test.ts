import { expect, it, vi } from 'vitest';
import type { PersonRef } from './api';

const { friendJoined } = vi.hoisted(() => ({ friendJoined: vi.fn() }));
vi.mock('./api', () => ({ api: { friendJoined } }));
vi.mock('./tg', () => ({ shareCard: vi.fn() }));
vi.mock('./i18n/index.svelte', () => ({ t: (k: string) => k }));
import { watchFriends } from './friends';

it('serializes slow invite polls and ignores responses after the sheet closes', async () => {
  vi.useFakeTimers();
  const page = { hidden: false }, joined = vi.fn();
  vi.stubGlobal('document', page);
  let answer!: (r: { at: number; usedBy: PersonRef | null }) => void;
  friendJoined.mockImplementation(() => new Promise((done) => { answer = done; }));
  let paused = false;
  const stop = watchFriends(joined, () => paused);
  const person: PersonRef = { id: 7, name: 'Student', avatar: null, founder: false };
  try {
    await vi.advanceTimersByTimeAsync(10_000);
    expect(friendJoined.mock.calls).toEqual([[0]]);
    answer({ at: 10, usedBy: person });
    await Promise.resolve();
    expect(joined).not.toHaveBeenCalled(); // the first response is only the baseline
    await vi.advanceTimersByTimeAsync(10_000);
    expect(friendJoined.mock.calls).toEqual([[0], [10]]);
    answer({ at: 11, usedBy: person });
    await Promise.resolve();
    expect(joined).toHaveBeenCalledExactlyOnceWith(person);
    paused = true;
    await vi.advanceTimersByTimeAsync(2500);
    paused = false; page.hidden = true;
    await vi.advanceTimersByTimeAsync(2500);
    expect(friendJoined).toHaveBeenCalledTimes(2);
    page.hidden = false;
    await vi.advanceTimersByTimeAsync(2500);
    expect(friendJoined.mock.calls).toEqual([[0], [10], [11]]);
    stop();
    answer({ at: 12, usedBy: person });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(joined).toHaveBeenCalledTimes(1);
    expect(friendJoined).toHaveBeenCalledTimes(3);
  } finally { stop(); vi.unstubAllGlobals(); vi.useRealTimers(); }
});
