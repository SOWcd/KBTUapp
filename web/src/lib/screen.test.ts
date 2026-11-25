import { afterEach, expect, it, vi } from 'vitest';
import { screenPoll, screenView } from './screen';

const bot = 'https://t.me/TestBot?startapp=';
const reply = (status: number, body: object) => ({ status, ok: status === 200, json: async () => body });

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('serializes polls and ignores an old pairing response after reconnect', async () => {
  vi.useFakeTimers();
  let finishOldPoll: (value: ReturnType<typeof reply>) => void = () => {};
  const oldPoll = new Promise<ReturnType<typeof reply>>((resolve) => { finishOldPoll = resolve; });
  const fetch = vi.fn()
    .mockReturnValueOnce(oldPoll)
    .mockResolvedValueOnce(reply(200, { code: 'new', bot, secret: 'new-secret', ttl: 120 }))
    .mockResolvedValueOnce(reply(200, { code: 'new', bot, left: 118 }));
  vi.stubGlobal('fetch', fetch);
  const storage = { getItem: () => 'old-secret', setItem: vi.fn(), removeItem: vi.fn() };
  vi.stubGlobal('sessionStorage', storage);
  vi.stubGlobal('localStorage', storage);
  const receive = vi.fn(), screen = screenPoll(receive);
  try {
    await vi.advanceTimersByTimeAsync(4000);
    expect(fetch).toHaveBeenCalledTimes(1);
    screen.again();
    await vi.advanceTimersByTimeAsync(0);
    finishOldPoll(reply(403, { message: 'screen' }));
    await vi.advanceTimersByTimeAsync(2000);
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch).toHaveBeenLastCalledWith('/api/screen', expect.objectContaining({ headers: { 'X-Screen': 'new-secret' } }));
    expect(receive.mock.calls.map(([state]) => state?.code ?? null)).toEqual([null, 'new', 'new']);
  } finally {
    screen.stop();
  }
});

it('hides both QR links when the screen lease or pairing code expires', () => {
  const pairing = { code: 'one', bot, expires: 15_000 };
  const live = { ...pairing, session: 1, param: 'ci_one' };
  expect(screenView(live, 14_999)).toMatchObject({ entry: bot + 'ci_one', pair: bot + 'sh_one' });
  for (const state of [pairing, live]) {
    expect(screenView(state, 15_000)).toMatchObject({ fresh: false, entry: '', pair: '' });
  }
});

it('shows total arrivals even when walk-ins push the count above the expected list', () => {
  const state = { code: 'one', bot, expires: 15_000, done: 11, expected: 10 };
  expect(screenView(state, 0)).toEqual({ fresh: true, entry: '', pair: bot + 'sh_one', arrivals: 11 });
});
