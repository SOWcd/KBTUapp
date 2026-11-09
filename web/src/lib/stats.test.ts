import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./tg', () => ({ inTelegram: true, onIos: true, onAndroid: false, on: () => () => {}, tg: { initData: 'signed' } }));

const DAY = 86_400_000, MIN = 60_000;
const noon = 20_000 * DAY + 7 * 3600_000; // 12:00 in Almaty
let send: ReturnType<typeof vi.fn>;
let hide: (hidden: boolean) => void;

/** The module afresh, as a new launch: `store` is the device's localStorage, null when it's blocked. */
async function launch(store: Record<string, string> | null) {
  vi.resetModules();
  const doc = { hidden: false, addEventListener: (_: string, f: () => void) => { hide = (h) => { doc.hidden = h; f(); }; } };
  vi.stubGlobal('document', doc);
  vi.stubGlobal('addEventListener', () => {});
  vi.stubGlobal('localStorage', { getItem: (k: string) => { if (!store) throw new Error('blocked'); return store[k] ?? null; }, setItem: (k: string, v: string) => { if (!store) throw new Error('blocked'); store[k] = v; } });
  return import('./stats');
}
const sent = () => send.mock.calls.map((c) => JSON.parse((c as unknown as [string, { body: string }])[1].body));

describe('usage counters', () => {
  beforeEach(() => {
    vi.useFakeTimers({ now: noon });
    send = vi.fn(() => Promise.reject(new Error('down')));
    vi.stubGlobal('fetch', send);
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('keeps the class of a start parameter, never its value', async () => {
    const { launchedFrom } = await launch(null);
    expect(['', 'ev_12_ABCDEFGHIJ', 'cl_3', 'fr_' + 'a'.repeat(24), 'r_ABCDEFGHIJ', 'ci_1_2_' + 'b'.repeat(16), 'friends'].map(launchedFrom))
      .toEqual(['from.none', 'from.event', 'from.club', 'from.friend', 'from.friend', 'from.qr', 'from.other']);
  });

  it('puts an open time in its bucket', async () => {
    const { bucketOf } = await launch(null);
    expect([999, 1000, 2999, 4999, 7999, 8000, 60000].map((ms) => bucketOf(ms))).toEqual([0, 1, 2, 3, 4, 5, 5]);
  });

  it('adds up in memory, sends once, and a failure is dropped', async () => {
    const { count, flush } = await launch(null);
    count('tab.afisha'); count('tab.afisha'); count('do.qr');
    flush(); flush();
    expect(sent()).toEqual([{ 'tab.afisha': 2, 'do.qr': 1 }]); // storage blocked: no uniq.*, it couldn't stay once a day
  });

  it('a session is the visible time until 30 s or more hidden', async () => {
    const store = {};
    const { flush } = await launch(store);
    vi.advanceTimersByTime(40_000); hide(true);
    vi.advanceTimersByTime(29_000); hide(false);             // back in under 30 s: the same session
    vi.advanceTimersByTime(40_000); hide(true);
    vi.advanceTimersByTime(30_000); hide(false);             // 80 s visible in all
    flush();
    expect(sent().flatMap(Object.entries)).toContainEqual(['sess.2', 1]);
    send.mockClear();
    vi.advanceTimersByTime(10_000); hide(true);              // this one ends with the app closed: the next launch sends it
    vi.advanceTimersByTime(60_000);
    const again = await launch(store);
    again.flush();
    expect(sent()).toEqual([{ 'sess.0': 1 }]);
  });

  it('sends one key for yesterday\'s visible time on the first open of the next day', async () => {
    const store = {};
    await launch(store);
    vi.advanceTimersByTime(7 * MIN); hide(true);
    vi.setSystemTime(noon + DAY);
    const next = await launch(store);
    next.flush(); next.flush();
    expect(sent().filter((b) => Object.keys(b).some((k) => k.startsWith('time.')))).toEqual([expect.objectContaining({ 'time.2': 1 })]);
  });

  it('a screen is counted once a day per device, and the flag stays on the device', async () => {
    const store: Record<string, string> = {};
    const one = await launch(store);
    one.count('sheet.event'); one.count('from.none'); one.flush();
    one.count('sheet.event'); one.flush();
    expect(sent()).toEqual([{ 'sheet.event': 1, 'from.none': 1, 'uniq.sheet.event': 1 }, { 'sheet.event': 1 }]);
    expect(JSON.parse(store['kb-stats']).u).toEqual(['sheet.event']);
    send.mockClear();
    vi.setSystemTime(noon + DAY);
    const two = await launch(store);
    two.count('sheet.event'); two.flush();
    expect(sent()).toEqual([{ 'sheet.event': 1, 'uniq.sheet.event': 1 }]);
  });

  it('a visit over midnight is split between the two days', async () => {
    vi.setSystemTime(noon + 12 * 3600_000 - 10 * MIN); // 23:50 in Almaty
    const store: Record<string, string> = {};
    const { flush } = await launch(store);
    vi.advanceTimersByTime(20 * MIN); hide(true);
    flush();
    expect(sent().flatMap(Object.entries)).toContainEqual(['time.3', 1]); // 10 min yesterday; the other 10 stay on today
    expect(JSON.parse(store['kb-stats']).ms).toBe(10 * MIN);
  });
});
